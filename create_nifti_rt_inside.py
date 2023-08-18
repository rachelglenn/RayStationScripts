import pydicom
from pydicom import dcmread
import os
import pandas as pd
import numpy as np
import re
import os

dicom_dir = '/rsrch1/ip/rglenn1/data/Methodist/RG_Export/'
nifty_dir = '/rsrch1/ip/rglenn1/data/Methodist/nifty/'
all_patient_dicom = os.listdir(dicom_dir)  
training_csv = '/rsrch1/ip/rglenn1/data/Methodist/Methodist-training.csv'

def create_nifti(single_pat_dir, out_dir, patient_dir,  dicom_list, nifti_list, patientID_list, series_case_list ):
  # Get the rtstuct and dicom directories
  
  dicom_folder = single_pat_dir
  rtstuct_files = [i for i in os.listdir(dicom_folder) if 'RS1.' in i] 
  
  path = os.path.normpath(single_pat_dir)
  split_path = path.split(os.sep)
  #print("check split_path", split_path)
    
  #print("dicom folder",  dicom_folder)
  #print("rtstructs", rtstuct_files)
    
  #Create the output directory structure:
  desc =   split_path[-2]
  desc = desc.replace("/", "_")
  desc = desc.replace(" ", "_") 
  desc = desc.replace("-", "_")  
  desc = desc.replace(",", "_")
  desc = desc.replace(":", "_")
  desc = desc.replace("(", "_")
  desc = desc.replace(")", "_")
  desc = desc.replace("=", "_")
  desc = desc.replace(".", "_")
  desc = desc.replace("&", "and")
  outdir = out_dir + '/' + split_path[-3] + '_'+  desc
  #print("outdir 1", outdir)
  patientID_list.append(split_path[-3])
  series_case_list.append( desc)

  #if not os.path.exists(outdira): os.mkdir(outdira)
  #outdirb = out_dir + '/' +
  #print("outdir 2", outdirb)
  #if not os.path.exists(outdirb): os.mkdir(outdirb)
  
  for rtstruct in rtstuct_files:
      cmd = 'dcmrtstruct2nii convert -r ' + dicom_folder + '/' + rtstruct + ' -d '+ dicom_folder + ' -o ' + outdir
      #success = os.system(cmd)
      print("\tExecuting cmd:", cmd)
      #print("success", success)
        
  print('------------------')

  nifti_list.append(outdir)
  dicom_list.append(dicom_folder)
  print("\n\n------------------------")

  return  dicom_list, nifti_list, patientID_list, series_case_list


dicom_list = []  
nifti_list = []
patientID_list = []
series_case_list = []

for patient_dir in all_patient_dicom:
  
  if patient_dir == 'patient_list.csv':
    continue
  patient_folders = os.listdir(dicom_dir + '/' + patient_dir) 
  for subfolder in patient_folders:
    #patient_dir = "LAB100008"

    single_pat_dir = dicom_dir + '/' + patient_dir + '/' + subfolder
    for sub_subfolder in os.listdir(single_pat_dir):
      dicom_folder  = single_pat_dir + '/' + sub_subfolder
      #print("\t Converting patient", dicom_folder)
      dicom_list, nifti_list, patientID_list, series_case_list = create_nifti(dicom_folder, nifty_dir, patient_dir, dicom_list, nifti_list, patientID_list, series_case_list)
  

# Create the csv file
image_list = ['']*len(nifti_list)
mask_list = ['']*len(nifti_list)
#phase_info = []
#patient_id =[]
#for x in nifti_list:
#  print(x)
for x in range(len(nifti_list)):
  directory = nifti_list[x]
  if os.path.exists(directory):
    nifti_list_temp = list(os.listdir(directory))
    print("nifti_dir:", nifti_list_temp)
    if len(nifti_list_temp) > 0:
      masks_temp = nifti_list_temp
      masks_temp.remove('image.nii.gz')
      masks  = [directory + x for x in masks_temp]  
      print("masks", masks)
      images = directory + "/image.nii.gz"
  

      image_list[x] = images
      mask_list[x] = masks
      #phase_info.append(split_path[-1])
      #patient_id.append(split_path[-2])
  
  else:
    print("No Niftis in the folder:", directory)
  
# Remove empty rows
#print("length check of dataframe", len(image_list), len(mask_list), len(phase_info), len(patient_id))
df = pd.DataFrame(
    {'id':patientID_list,
    'phase_info' :series_case_list, 
    'image': image_list,
     'mask': mask_list,
    })
filter_empty = df["image"] != ""

dfNew = df[filter_empty]

dfNew.to_csv(training_csv)



