
import SimpleITK as sitk
import sys
import os
import subprocess
import pandas as pd

Methodist_training_csv = "/rsrch1/ip/rglenn1/data/Methodist/Methodist-training.csv"
training_csv = "/rsrch1/ip/rglenn1/data/Methodist/Methodist-training_bias.csv"

# Must enter in terminal prior to running
#os.system("export PATH=/rsrch1/ip/rglenn1/quantumSegmentation/MICO_v0/antsbuild/install/bin:$PATH")
#os.system("export LD_LIBRARY_PATH=/rsrch1/ip/rglenn1/quantumSegmentation/MICO_v0/antsbuild/install/lib:$LD_LIBRARY_PATH")

def correctAllImages(patient, phase):

	
	orginial_nifti = patient + "/" + phase + ".nii.gz"
	save_nifti =  patient + "/" + phase +  ".bc.nii.gz"
	save_bias_nifti =  patient + "/" + phase +  "BiasField.nii.gz"
	command_str = "N4BiasFieldCorrection -v 1 -d 3 -c [20x20x20x10,0] -b [200] -s 2 -i "
	# -d dimensionality 3 = 3D
	# -v verbose (0)/1
	# -c --convergence [<numberOfIterations=50x50x50x50>,<convergenceThreshold=0.0>]
	#   Convergence is determined by calculating the coefficient of variation between 
	#   subsequent iterations. When this value is less than the specified threshold from 
	#   the previous iteration or the maximum number of iterations is exceeded the 
	#   program terminates. Multiple resolutions can be specified by using 'x' between 
	#   the number of iterations at each resolution, e.g. 100x50x50.
	# -s --shrink-factor 1/2/3/(4)/...
	#   Running N4 on large images can be time consuming. To lessen computation time, 
	#   the input image can be resampled. The shrink factor, specified as a single 
	#   integer, describes this resampling. Shrink factors <= 4 are commonly used.Note 
	#   that the shrink factor is only applied to the first two or three dimensions 
	#   which we assume are spatial.
	# -b --bspline-fitting [splineDistance,<splineOrder=3>]
	#[initialMeshResolution,<splineOrder=3>]
	#   These options describe the b-spline fitting parameters. The initial b-spline 
	#   mesh at the coarsest resolution is specified either as the number of elements in 
	#   each dimension, e.g. 2x2x3 for 3-D images, or it can be specified as a single 
	#   scalar parameter which describes the isotropic sizing of the mesh elements. The 
	#   latter option is typically preferred. For each subsequent level, the spline 
	#   distance decreases in half, or equivalently, the number of mesh elements doubles 
	#   Cubic splines (order = 3) are typically used. The default setting is to employ a 
	#   single mesh element over the entire domain, i.e., -b [1x1x1,3].
	command_str = "N4BiasFieldCorrection -d 3 -v 1 -s 4 -b [ 180 ] -c [ 50x50x50x50, 0.0 ]   -i "
	text = [command_str, orginial_nifti, " -o "," [ ", save_nifti,", ", save_bias_nifti, " ]"]
	print(" ".join(text))
	
	
	#os.system(" ".join(text))
	

patient_images = pd.DataFrame(pd.read_csv(Methodist_training_csv))
print(patient_images)
for patient in list(patient_images['image']):
  head_tail = os.path.split(patient)
  correctAllImages(head_tail[0], "image")

bias_correction_list = []
bias_field_list = []
image_list = []
masks_list = []
series_case_list = []
patientID_list = []
for patient in list(patient_images['image']):
  head_tail = os.path.split(patient)
  
  
  nifti_list_temp = list(os.listdir(head_tail[0]))
  masks_temp = nifti_list_temp
  masks_temp.remove('image.nii.gz')
  masks_temp.remove('image.bc.nii.gz')
  masks  = [head_tail[0] + x for x in masks_temp]  
  
  bias_correction_list.append(head_tail[0] + "/image.bc.nii.gz")
  masks_list.append(masks)
  image_list.append(head_tail[0] + "/image.nii.gz")
  series_case_list.append(os.path.split(head_tail[0])[-1])
  bias_field_list.append(head_tail[0] + "/BiasField.nii.gz")
  patientID_list.append(head_tail[0][:9])



df = pd.DataFrame(
    {'id':patientID_list,
    'phase_info' :series_case_list, 
    'image': image_list,
    'bias corr' : bias_correction_list,
    'bias_field' : bias_field_list,
     'mask': masks_list,
    })
filter_empty = df["image"] != ""

dfNew = df[filter_empty]

dfNew.to_csv(training_csv)

# example
#/opt/apps/ANTS/build/ANTS-build/Examples/N4BiasFieldCorrection -v 1 -d 3 -c [20x20x20x10,0] -b [200] -s 2 -i  bcmdata/BCM0041013/Ven.bias.nii.gz  -o  bcmdata/
#BCM0041013/Ven.bias.nii.gz
