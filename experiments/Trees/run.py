#Experiment
from comet_ml import Experiment
from datetime import datetime
from DeepTreeAttention.trees import AttentionModel
from DeepTreeAttention.utils import metrics, resample, start_cluster
from DeepTreeAttention.models.layers import WeightedSum
from DeepTreeAttention.visualization import visualize
from tensorflow.keras import metrics as keras_metrics
from tensorflow.keras.models import load_model
from random import randint
from time import sleep
from distributed import wait

import glob
import os
import numpy as np
import matplotlib.pyplot as plt
import pandas as pd

def find_shapefiles(dirname):
    files = glob.glob(os.path.join(dirname,"*.shp"))
    return files

def predict(dirname, savedir, generate=True, cpus=2, parallel=True, height=40, width=40, channels=3):
    """Create a wrapper dask cluster and run list of shapefiles in parallel (optional)
        Args:
            dirname: directory of DeepForest predicted shapefiles to run
            savedir: directory to write processed shapefiles
            generate: Do tfrecords need to be generated/overwritten or use existing records?
            cpus: Number of dask cpus to run
    """
    shapefiles = find_shapefiles(dirname=dirname)
    
    if parallel:
        client = start_cluster.start(cpus=cpus)
        futures = client.map(_predict_,shapefiles, create_records=generate, savedir=savedir, height=height, width=width, channels=channels)
        wait(futures)
        
        for future in futures:
            print(future.result())
    else:
        for shapefile in shapefiles:
            _predict_(shapefile, model_path, savedir=savedir, create_records=generate)
            
if __name__ == "__main__":
    experiment = Experiment(project_name="neontrees", workspace="bw4sz")

    #Create output folder
    #Sleep for a moment to allow queries to build up in SLURM queue
    sleep(randint(0,10))
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    save_dir = "{}/{}".format("/orange/idtrees-collab/DeepTreeAttention/snapshots/",timestamp)
    os.mkdir(save_dir)
    
    experiment.log_parameter("timestamp",timestamp)
    
    #Create a class and run
    model = AttentionModel(config="/home/b.weinstein/DeepTreeAttention/conf/tree_config.yml")
    model.create()
        
    #Log config
    experiment.log_parameters(model.config["train"])
    experiment.log_parameters(model.config["evaluation"])    
    experiment.log_parameters(model.config["predict"])
    
    ##Train
    #Train see config.yml for tfrecords path with weighted classes in cross entropy
    model.read_data()
    class_weight = model.calc_class_weight()
    
    #Load from file or train new models
    if model.config["train"]["checkpoint_dir"] is not None:
        dirname = model.config["train"]["checkpoint_dir"]
        model.RGB_model = load_model("{}/RGB_model.h5".format(dirname), custom_objects={"WeightedSum": WeightedSum})
        model.HSI_model = load_model("{}/RGB_model.h5".format(dirname), custom_objects={"WeightedSum": WeightedSum})
    else:
        ##Train subnetworks
        experiment.log_parameter("Train subnetworks", True)
        with experiment.context_manager("RGB_spatial_subnetwork"):
            print("Train RGB spatial subnetwork")
            model.read_data(mode="RGB_submodel")
            model.train(submodel="spatial", sensor="RGB", class_weight=[class_weight, class_weight, class_weight], experiment=experiment)
            
        with experiment.context_manager("RGB_spectral_subnetwork"):
            print("Train RGB spectral subnetwork")    
            model.read_data(mode="RGB_submodel")   
            model.train(submodel="spectral", sensor="RGB", class_weight=[class_weight, class_weight, class_weight], experiment=experiment)
                
        #Train full RGB model
        with experiment.context_manager("RGB_model"):
            experiment.log_parameter("Class Weighted", True)
            model.read_data(mode="RGB_train")
            model.train(class_weight=class_weight, sensor="RGB", experiment=experiment)
            model.RGB_model.save("{}/RGB_model.h5".format(save_dir))
            
            #Get Alpha score for the weighted spectral/spatial average. Higher alpha favors spatial network.
            if model.config["train"]["RGB"]["weighted_sum"]:
                estimate_a = model.RGB_model.get_layer("weighted_sum").get_weights()
                experiment.log_metric(name="spatial-spectral weight", value=estimate_a[0][0])
        
        ##Train subnetwork
        experiment.log_parameter("Train subnetworks", True)
        with experiment.context_manager("HSI_spatial_subnetwork"):
            print("Train HSI spatial subnetwork")
            model.read_data(mode="HSI_submodel")
            model.train(submodel="spatial", sensor="hyperspectral",class_weight=[class_weight, class_weight, class_weight], experiment=experiment)
        
        with experiment.context_manager("HSI_spectral_subnetwork"):
            print("Train HSI spectral subnetwork")    
            model.read_data(mode="HSI_submodel")   
            model.train(submodel="spectral", sensor="hyperspectral", class_weight=[class_weight, class_weight, class_weight], experiment=experiment)
                
        #Train full model
        with experiment.context_manager("HSI_model"):
            experiment.log_parameter("Class Weighted", True)
            model.read_data(mode="HSI_train")
            model.train(class_weight=class_weight, sensor="hyperspectral", experiment=experiment)
            model.HSI_model.save("{}/HSI_model.h5".format(save_dir))
            
            #Get Alpha score for the weighted spectral/spatial average. Higher alpha favors spatial network.
            if model.config["train"]["HSI"]["weighted_sum"]:
                estimate_a = model.HSI_model.get_layer("weighted_sum").get_weights()
                experiment.log_metric(name="spatial-spectral weight", value=estimate_a[0][0])
            
    ##Ensemble
    with experiment.context_manager("ensemble"):    
        print("Train Ensemble")
        model.ensemble(freeze=model.config["train"]["ensemble"]["freeze"], experiment=experiment)
    
    #Save model
    model.ensemble.save("{}/Ensemble.h5".format(save_dir))


    
    
