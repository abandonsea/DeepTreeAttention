#Patches
import rasterio

def row_col_from_crown(crown, src):
    """Given a geometry object and rasterio src, get the row col indices of all overlapping pixels
    Args:
        crown: shapely geometry box
        img_centroids: a list of (row, col) indices for the rasterio src object
    """
    left, bottom, right, top = crown.bounds 
    img_centroids = []
    img = src.read(window=rasterio.windows.from_bounds(left, bottom, right, top, transform=src.transform))
    win_transform = src.window_transform(window=rasterio.windows.from_bounds(left, bottom, right, top, transform=src.transform))
    for row in range(img.shape[1]):
        for col in range(img.shape[2]):
            coords = rasterio.transform.xy(win_transform, row, col, offset='center')
            row_col = rasterio.transform.rowcol(src.transform, coords[0], coords[1])
            img_centroids.append(row_col)    
    
    return img_centroids
                    
def crown_to_pixel(crown, img_path, savedir, basename,width=11, height=11):
    """Given a crown box, create the pixel crops
    Args:
         crown: a geometry object
         img_path: sensor data to crop
         savedir: location to save crops
         basename: output file is {basename}_{counter}.tif for each pixel crop
         width: pixel size crop in x
         height: pixel size in y
    Returns:
         crown_patches: filenames of written patches
    """
    counter = 0
    crown_patches = []    
    src = rasterio.open(img_path)    
    img_centroids = row_col_from_crown(crown, src)
    for indices in img_centroids:
        row, col = indices
        img = src.read(window = rasterio.windows.Window(col_off=col, row_off=row, width = width, height=height), boundless=False)
        filename = "{}/{}_{}.tif".format(savedir, basename, counter)
        with rasterio.open(filename, "w", driver="GTiff",height=height, width=width, count = img.shape[0], dtype=img.dtype) as dst:
            dst.write(img)
        counter = counter + 1
        crown_patches.append(filename)

    return crown_patches
