
import os
import sys
import json
import time
import shutil
from os import mkdir, path, chdir, getcwd
import logging
import pydicom
import datetime
import platform
import pandas as pd
import traceback
import importlib
import subprocess
import urllib.request as requests
from urllib.parse import urlencode
from http.cookiejar import CookieJar
from pydicom.datadict import dictionary_VR
export_folder = r'\\R1pwpsrgxnat2\fuentes_lab\FUENTES_LAB_DATA\PA14-0646-downloaded\temp'	
export_folder = r'\\R1pwpsrgxnat2\fuentes_lab\RayStation\RG_Export'

py_imp = platform.python_implementation()
if py_imp != 'CPython':
    print('Python interpreter should be CPython, but {} was detected'.format(py_imp))
    sys.exit()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    handlers=[logging.StreamHandler(sys.stdout)])
logging.captureWarnings(True)

from connect import *
clr.AddReference('System')
from System import Environment
from System.Windows.Forms import (
    Form,
    Label,
    Screen,
    Button,
    Padding,
    TextBox,
    CheckBox,
    ComboBox,
    FlatStyle,
    MessageBox,
    AnchorStyles,
    DialogResult,
    ComboBoxStyle,
    MessageBoxIcon,
    OpenFileDialog,
    TableLayoutPanel,
    MessageBoxButtons,
    FormStartPosition,
    FolderBrowserDialog,
    TableLayoutPanelGrowStyle,
    CheckedListBox,
    ItemCheckEventHandler
)
from System.Drawing import (
    Font,
    Size,
    Color,
    FontStyle,
    ContentAlignment
)

class XnatConnection:
    def __init__(self,host):
        self.host = host
        self.is_connected = False
        self.cookie_jar = requests.HTTPCookieProcessor(CookieJar())
        self.opener = requests.build_opener(self.cookie_jar)
        requests.install_opener(self.opener)
        self.connect()

    def __del__(self):
        self.exit()

    def __getattr__(self,method):
        def req(url,as_raw=False,to_json=False,return_bool=False,**kwargs):
            req_type = str(method).upper()
            req = requests.Request(self.host+url,method=req_type,**kwargs)
            req.add_header('Authorization','Basic cmF5c3RhdGlvbl9hcGk6M0hSRDE1eXN0M201QFBJ')
            res = requests.urlopen(req)
            if res.status >= 300: 
                err = ''
                try:
                    err = res.read().decode('utf-8')
                except: pass
                raise Exception('Server returned error code {}: {}'.format(res.status,err))
            if return_bool: return True
            res = res.read()
            if not as_raw: 
                res = res.decode('utf-8')
                if to_json: res = json.loads(res)
            return res
        return req

    def connect(self):
        try:
            r = self.get('/data/JSESSION',to_json=False)
            if r:
                self.is_connected = True
                logging.info('Successfully connected to XNAT')
        except Exception as ex:
            logging.error('Unable to connect to XNAT: {}'.format(ex))

    def exit(self):
        if not self.is_connected: return
        try:
            self.delete('/data/JSESSION')
        except: pass 
        self.is_connected = False

    def gradual_upload(self,path,project_id,subject_id,session_id):
        try:
            url = '/data/services/import?inbody=true'
            url += '&PROJECT_ID={}&SUBJECT_ID={}&EXPT_LABEL={}'.format(project_id,subject_id,session_id)
            url += '&import-handler=gradual-DICOM&Direct-Archive=true'
            headers = {'Content-Type':'application/x-www-form-urlencoded'}
            with open(path,'rb') as f:
                res = self.post(url,return_bool=True,data=f.read(),headers=headers)
            if res: return True
        except Exception as ex:
            logging.error('Error uploading zip archive: {}'.format(ex))
        return False

    def set_prearchive_code(self,project_id,code_id=5):
        try:
            url = '/REST/projects/{}/prearchive_code/{}'.format(project_id,code_id)
            res = self.put(url,return_bool=True)
            if res: return True
        except Exception as ex:
            logging.error('Unable to set prearchive code: {}'.format(ex))
        return False

class PatientLoader:
    def __init__(self,fid=''):
        self.db = get_current('PatientDB')
        self.pid = None
        self.case = None
        self.patient = None
        self.patients = {}
        self.pid_list = []
        self.case_ids = {}
        self.series_uids = []
        self.dicom_dir = ''
        self.valid_modalities = ['CT','MR','PT','RTSTRUCT']
        self.sop_uids = {getattr(pydicom.uid,i):i for i in dir(pydicom.uid) if i.endswith('Storage')}
        valid_pids = []
        if fid: 
            self.search(fid)
            valid_pids = [i for i in self.pid_list]
        if valid_pids: self.patients = {k:v for k,v in self.patients.items() if k in valid_pids}

    def search(self,fid):
        if not fid:
            try:
                self.patient = get_current('Patient')
                self.pid = self.patient.PatientID
                self.case = get_current('Case')
                self.patients[pid] = self.patient
            except: pass
            return

        self.pid_list = []
        if os.path.exists(fid):
            logging.info('Loading patients from {}'.format(fid))

            if os.path.isdir(fid):
                self.search_directory(fid)
            else:
                self.load_file(fid)

            self.pid_list = list(set([i for i in self.pid_list if i.replace(' ','')]))
            if not self.pid_list:
                logging.info('No patients found in {}'.format(fid))
            else:
                logging.info('Found {} patient(s) in {}. Loading data...'.format(len(self.pid_list),fid))
        else:
            if ',' in str(fid):
                for i in str(fid).split(','):
                    i = i.replace(' ','')
                    if not i: continue
                    if i in self.pid_list: continue
                    try:
                        mrn = int(i)
                    except:
                        logging.warning('Patient ID is not numerical: "{}". If this is correct, you can ignore this message.'.format(i))
                    self.pid_list.append(i)
                logging.info('Searching for {} patient(s)'.format(len(self.pid_list)))
            else:
                try:
                    mrn = int(fid)
                except:
                    logging.warning('Patient ID is not numerical: "{}". If this is correct, you can ignore this message.'.format(fid))
                self.pid_list.append(str(fid))


        for i in self.pid_list:
            self.find_patient(i)

    def search_directory(self,path):
        self.pid_list = []
        paths = {}
        for root,_,files in os.walk(path):
            dcms = [f for f in files if f.endswith('.dcm')]
            if not dcms: continue
            pid = self.get_dcm_tag(os.path.join(root,dcms[0]),'PatientID')
            if pid:
                paths[root] = pid
                if pid not in self.pid_list: self.pid_list.append(pid)

        for pid in self.pid_list:
            roots = [k for k,v in paths.items() if v == pid]
            if not roots: continue

            root = roots[0]
            if len(roots) > 1:
                max_n = 0
                r_parts = []
                for r in roots[0].split(os.sep):
                    r_parts.append(r)
                    n = len([i for i in roots if os.sep.join(r_parts) in i])
                    if n < max_n: break
                    max_n = n
                    root = os.sep.join(r_parts)

            if root.replace(os.sep,''):
                self.patients[pid] = self.find_patient(pid,only_query=True)
                self.patients[pid].update({
                    'path': root,
                    'found': True
                })

    def load_file(self,path):
        self.pid_list = []
        with open(path,'r') as f:
            for line in f:
                for i in line.replace('\n','').split(','):
                    i = i.replace(' ','')
                    if not i: continue
                    if i in self.pid_list: continue
                    try:
                        mrn = int(i)
                    except:
                        logging.warning('Patient ID is not numerical: "{}". If this is correct, you can ignore this message.'.format(i))
                    self.pid_list.append(i)

    def load_from_db(self,pid,info):
        for i in info:
            last_name = i['LastName'].split('_')[-1]
            if not last_name: continue
            if i['PatientID'] != pid: continue
            if last_name in [str(i) for i in range(5)]: continue
            try:
                p = self.db.LoadPatient(PatientInfo=i, AllowPatientUpgrade=True)
                patient_id = p.PatientID
                case = p.Cases[0]
                model = case.PatientModel
                self.patient = p
                self.case = case
                self.case.SetCurrent()
                for c in self.patient.Cases:
                    for e in c.Examinations:
                        data = e.GetAcquisitionDataFromDicom()
                        sid = str(data['StudyModule']['StudyID'])
                        suid = str(data['SeriesModule']['SeriesInstanceUID'])
                        self.case_ids[sid] = c.CaseName
                        self.series_uids.append(suid)
                return
            except: pass

    def load_patient(self,pid,only_query=False,return_patient=False):
        self.patient = None
        self.case = None
        p = self.find_patient(pid,only_query)
        if not isinstance(p,dict):
            if p is None: return False
            if return_patient: return p
            return True

        if only_query: return p['found']
        if not p['found']: return False

        if p['info']:
            self.load_from_db(pid,p['info'])
            if self.patient is not None: 
                p['loaded'] = True
                logging.info('Loaded patient from DB: {}'.format(pid))

        if p['path']:
            p['loaded'] = False
            try:
                self.patient = self.import_from_path(p['path'],str(pid))
                if self.patient is not None: 
                    p['loaded'] = True
                    logging.info('Patient {} loaded from path'.format(pid))
            except Exception as ex:
                format_error('Unable to load patient {}: {}'.format(pid,ex))

        if self.patient is None: 
            logging.warning('Unable to find patient: {}'.format(pid))
            return False
        elif not p['loaded']:
            logging.warning('Unable to load patient: {}'.format(pid))
            return False
        elif return_patient: 
            return self.patient
        return True

    def find_patient(self,pid,only_query=False):
        if pid in self.patients: return self.patients[pid]
        res = {'info':[],'path':'','found':False,'loaded':False}
        logging.info('Searching for patient: {}'.format(pid))
        p_info = self.db.QueryPatientInfo(Filter={'PatientID':pid})
        p_info = [p for p in p_info if p['PatientID'] == pid]
        if not p_info: p_info = self.db.QueryPatientInfo(Filter={'PatientID':pid}, UseIndexService=True)
        p_info = [p for p in p_info if p['PatientID'] == pid]
        if p_info: 
            logging.info('Patient found in database.')
            res.update({
                'info': p_info,
                'found': True
            })
        else:
            logging.info('Patient not found in database.')

        if not only_query and self.dicom_dir:
            for root,_,_ in os.walk(self.dicom_dir):
                if not root.endswith(str(pid)): continue
                logging.info('Found patient directory: {}'.format(root))
                res.update({
                    'path': root,
                    'found': True
                })
                break

        if not res['found']:
            if not only_query: logging.warning('Unable to find patient in database or file path')
            return res

        self.patients[pid] = res
        return res

    def format_warning(self,msg):
        res = ''
        try:
            w = [str(i) for i in json.loads(msg)['Warnings']]
            if w: res = '\n'.join(w)
        except: pass
        return res

    def get_dcm_tag(self,path,key,default=''):
        try:
            ds = pydicom.dcmread(path,specific_tags=[key])
            return str(ds.get(key,default))
        except Exception as ex: 
            print(ex)
            pass
        return default

    def get_series_query(self,dcm):
        try:
            ds = pydicom.dcmread(dcm,specific_tags=['PatientID','StudyInstanceUID','Modality','StudyID'])
            return {
                'StudyID': str(ds.StudyID),
                'Modality': str(ds.Modality),
                'PatientID': str(ds.PatientID),
                'StudyInstanceUID': str(ds.StudyInstanceUID)
            }
        except: pass

    def verify_positions(self,dcms):
        try:
            pos = ''
            for f in os.scandir(dcms):
                ds = pydicom.dcmread(f.path,specific_tags=['ImageOrientationPatient'])
                new_pos = str(['{:.3f}'.format(i) for i in ds.ImageOrientationPatient])
                if not pos:
                    pos = new_pos
                elif pos != new_pos:
                    return False
        except: pass
        return True

    def verify_sop_uid(self,path,return_val=False):
        try:
            ds = pydicom.dcmread(path,specific_tags=['SOPClassUID'])
            if return_val: return ds.SOPClassUID
            if '1.2.840.10008.5.1.4.1.1.7' in ds.SOPClassUID: return False
            return True
        except: pass
        return False

    def import_from_path(self,patient_path,pid):
        logging.info('Loading patient {} from path: {}'.format(pid,patient_path))

        try:
            if self.patient.PatientID != pid: self.patient = None
        except: pass

        if self.patient is not None:
            self.case = self.patient.Cases[0]
            logging.info('Patient already exists. Updating information.')
        else:
            logging.info('Patient does not exist. Creating new case.')

        dcm_paths = []
        dcm_studies = {}
        manufacturer = ''
        study_count = 0
        for root,_,files in os.walk(patient_path):
            dcms = [f for f in files if f.endswith('.dcm')]
            if dcms:
                fn = os.path.join(root,dcms[0])
                series_query = self.get_series_query(fn)
                # sid = series_query['StudyID']
                sid = series_query['StudyInstanceUID']
                if not str(sid).replace(' ',''): 
                    logging.info('Skipping {}: No Study ID found.'.format(root))
                    continue
                elif series_query['PatientID'] != pid:
                    logging.info('Skipping {}: Invalid patient ID "{}".'.format(root,series_query['PatientID']))
                    continue
                elif series_query['Modality'] not in self.valid_modalities:
                    logging.info('Skipping {}: Invalid modality "{}"'.format(root,series_query['Modality']))
                    continue
                
                if not self.verify_sop_uid(fn):
                    sop_uid = self.verify_sop_uid(fn,return_val=True)
                    if sop_uid in self.sop_uids:
                        sop_name = self.sop_uids[sop_uid]
                        logging.info('Skipping {}: Invalid SOP Class UID {} ({})'.format(root,sop_uid,sop_name))
                    else:
                        logging.info('Skipping {}: Invalid SOP Class UID {}'.format(root,sop_uid))
                    continue
                if not self.verify_positions(root):
                    logging.info('Skipping {}: Inconsistent image orientations found in series.'.format(root))
                    continue

                if sid not in dcm_studies:
                    study_count += 1
                    c_name = None
                    if sid in self.case_ids: c_name = self.case_ids[sid]
                    dcm_studies[sid] = {
                        'name':c_name,
                        'series':[],
                        'rt_series': [],
                        'dti_series':[]
                    }
                if not manufacturer: manufacturer = self.get_dcm_tag(fn,'Manufacturer')
                dcm_paths.append([sid,series_query,root])

        logging.info('Found {} series ({} studies) in patient directory'.format(len(dcm_paths),len(dcm_studies)))

        if "siemens" in manufacturer.lower():
            s_tags = [[0x0019,0x100C],[0x0019,0x100E]]
        elif "philips" in manufacturer.lower():
            s_tags = [[0x0018,0x9087],[0x0018,0x9089]]
        else:
            s_tags = [[0x0043,0x1039],[0x0019,0x10BC],[0x0019,0x10BB],[0x0019,0x10BD]]

        if not dcm_paths:
            logging.warning('No DICOMs found in patient path: {}'.format(patient_path))
            return None

        for sid,query,path in dcm_paths:
            if query['PatientID'] != pid: continue
            uid = query['StudyInstanceUID']
            mod = query['Modality']
            series = self.db.QuerySeriesFromPath(Path=path,SearchCriterias={'PatientID':pid,'StudyInstanceUID':uid,'Modality':mod})
            for s in series:
                if s['Modality'] not in self.valid_modalities: continue
                if s['PatientID'] != pid: continue
                if s['SeriesInstanceUID'] in self.series_uids: 
                    logging.info('Skipping series {}: already exists.'.format(s['SeriesNumber']))
                    continue
                s_info = {
                    'PatientID': str(s['PatientID']),
                    'SeriesInstanceUID': str(s['SeriesInstanceUID']),
                    'StudyInstanceUID': str(s['StudyInstanceUID'])
                }
                info = ([s_info],path)
                if 'DTI' in str(s['SeriesDescription']).upper():
                    dcm_studies[sid]['dti_series'].append(info)
                elif s['Modality'] == 'RTSTRUCT':
                    dcm_studies[sid]['rt_series'].append(info)
                else:
                    dcm_studies[sid]['series'].append(info)

        seen_cases = []
        for sid,info in dcm_studies.items():
            logging.info('Importing study: {}'.format(sid))
            for s,path in info['series']:
                if self.patient is None:
                    self.case = None
                    try:
                        warnings = self.db.ImportPatientFromPath(Path=path,SeriesOrInstances=s)
                        # if warnings: continue
                        logging.info('Successfully imported patient')
                        self.patient = get_current('Patient')
                        if info['name'] is None:
                            self.case = self.patient.Cases[0]
                            info['name'] = self.case.CaseName
                        else:
                            self.case = [c for c in self.patient.Cases if c.CaseName == info['name']][0]
                        self.patient.Save()
                    except: pass
                else:
                    if info['name'] is None:
                        logging.info('Adding new case: {}'.format(info))
                    else:
                        logging.info('Loading {} data series for {}...'.format(len(s),info['name']))

                    try:
                        warnings = self.patient.ImportDataFromPath(Path=path,SeriesOrInstances=s,CaseName=info['name'])
                        # if warnings: continue
                        self.patient.Save()
                        self.case = [c for c in self.patient.Cases if c.CaseName not in seen_cases][0]
                        if info['name'] is None:
                            logging.info('Changed case to {}'.format(self.case.CaseName))
                            info['name'] = self.case.CaseName
                    except: pass

            for s,path in info['dti_series']:
                if self.patient is None:
                    self.case = None
                    try:
                        warnings = self.db.ScriptableDicom4DImagePatientImport(ImportFolderPath=path, 
                                                                                SeriesOrInstances=s, 
                                                                                DicomFilter='',
                                                                                SeparatingTags=s_tags)
                        # if warnings: continue
                        logging.info('Successfully imported patient')
                        self.patient = get_current('Patient')
                        self.case = self.patient.Cases[0]
                        self.patient.Save()
                    except: pass
                else:
                    if info['name'] is None:
                        self.case = get_current('Case')
                        info['name'] = self.case.CaseName
                    logging.info('Loading {} DTI series for {}...'.format(len(s),self.case.CaseName))
                    logging.info('Using separating tags: {}'.format(s_tags))
                    try:
                        warnings = self.case.ScriptableDicom4DImageImport(ImportFolderPath=path, 
                                                                            SeriesOrInstances=s, 
                                                                            DicomFilter='',
                                                                            SeparatingTags=s_tags)
                        # if warnings: continue
                        self.patient.Save()
                    except: pass

            for s,path in info['rt_series']:
                if self.patient is None:
                    logging.info('Skipping {}: No patient loaded to assign contours to.'.format(path))
                    continue

                if info['name'] is None:
                    self.case = get_current('Case')
                    info['name'] = self.case.CaseName

                logging.info('Loading RT data series for {}...'.format(info['name']))
                try:
                    warnings = self.patient.ImportDataFromPath(Path=path,SeriesOrInstances=s,CaseName=info['name'])
                    # if warnings: continue
                    self.patient.Save()
                except: pass

            if self.case.CaseName not in seen_cases: seen_cases.append(self.case.CaseName)

        # print('LOADED PATIENT: {}'.format(True if self.patient is not None else False))
        if self.patient is None: return None
        logging.info('Successfully loaded patient {}'.format(pid))
        self.patient.Save()
        return self.patient

class InputUI:
    def __init__(self):
        self.patient_input = ''
        self.patient_directory = ''
        self.form = None
        self.table = None
        self.inputs = []
        self.labels = {}
        self.status = False
        self.check_list = None
        self.check_toggle_cb = None
        self.browse_root = ''

    def __del__(self):
        if self.form is not None:
            self.form.Dispose()

    def to_ascii(self,txt):
        if not isinstance(txt,str): txt = str(txt)
        try:
            return txt.encode('ascii','ignore').decode()
        except:
            return txt

    def make_screen(self,title):
        self.status = False
        self.inputs = []
        self.labels = {}

        self.form = Form()
        self.form.AutoSize = True
        self.form.MaximumSize = Size(400,Screen.PrimaryScreen.WorkingArea.Bottom)
        self.form.StartPosition = FormStartPosition.CenterScreen
        self.form.Padding = Padding(0)
        self.form.Text = title
        self.form.AutoScroll = True
        self.form.BackColor = Color.White
        self.form.TopMost = True

        self.table = TableLayoutPanel()
        self.table.ColumnCount = 1
        self.table.RowCount = 1
        self.table.GrowStyle = TableLayoutPanelGrowStyle.AddRows
        self.table.Padding = Padding(0, 0, 0, 10)
        self.table.BackColor = Color.White
        self.table.AutoSize = True
        self.form.Controls.Add(self.table)

    def clear_inputs(self):
        for i in self.inputs:
            try:
                attr = i['attr']
                if attr is None: continue
                setattr(attr,'')
            except: pass
        self.inputs = []

    def show_import_screen(self,patient_id=''):
        self.patient_input = patient_id
        self.make_screen('Patient Importer')
        self.add_label('Select one or more patients to import to RayStation')
        self.add_patient_input()
        self.add_footer_buttons()
        self.form.ShowDialog()

    def exam_to_int(self,exam):
        val = '{}'.format(exam)
        try:
            val = int(exam.split(' ')[-1])
        except: pass

        if isinstance(val,str):
            try:
                val = ''
                for s in str(exam):
                    if s.isdigit(): val += s
                val = int(val)
            except: 
                val = 0
        return val

    def show_confirmation(self, patientid, exams,case_name):
        self.make_screen('Export Confirmation')
        exams = {k:exams[k] for k in sorted(exams.keys(),key=lambda x:self.exam_to_int(x))}
        protos = list(set([v['proto'] for v in exams.values()]))
        n_exams = len(exams)
        n_rtss = sum([len(v['rtss']) for v in exams.values()])
        label = 'Verfiy the following exports:\n\n'
        label += 'patient name {}\n'.format(patientid)
        label += '  - {}\n'.format(case_name)
        label += '  - {} Exams\n'.format(n_exams)
        label += '  - {} RT Structs\n'.format(n_rtss)
        label += '  - Protocols: {}'.format(', '.join(protos))
        self.add_label(label,is_bold=True)

        cb_list = []
        for k,v in exams.items():
            attr = 'exam_{}'.format(k)
            desc = '{} ({})'.format(k,v['desc'])
            cb_list.append([attr,k,desc])
            for r,rn in v['rtss']:
                attr = 'rtss_{}'.format(r)
                desc = '{} RT ({})'.format(r,rn)
                cb_list.append([attr,r,desc])
        self.add_checkbox_list('Select Exports',cb_list)

        self.add_footer_buttons()
        self.form.ShowDialog()

    def toggle_checks(self,val):
        if self.check_list is None: return
        n_items = self.check_list.Items.Count
        for i in range(n_items):
            self.check_list.SetItemChecked(i,val)

        if val:
            self.check_list.Text = 'Uncheck All'
        else:
            self.check_list.Text = 'Check All'

    def set_attr(self,obj,event):
        try:
            key = obj.Tag
            if isinstance(obj,CheckBox):
                if key == 'check_toggle':
                    self.toggle_checks(obj.Checked)
                else:
                    val = obj.Checked
            else:
                val = self.to_ascii(obj.Text)
            setattr(self,key,val)
        except: pass

    def check_list_handler(self,obj,event):
        idx = event.Index
        val = True if event.NewValue else False
        name = [i for i in obj.Items][idx]

        for i in self.inputs:
            if i['type'] != 'check': continue
            if i['input'] == name: 
                setattr(self,i['attr'],val)
                break

        if self.check_toggle_cb is None: return

        n_checked = 1 if val else -1
        n_checked += self.check_list.CheckedItems.Count
        if n_checked == 0:
            self.check_toggle_cb.Text = 'Check All'
            self.check_toggle_cb.Checked = False
        elif n_checked == self.check_list.Items.Count:
            self.check_toggle_cb.Text = 'Uncheck All'
            self.check_toggle_cb.Checked = True

        # print('{} ({}): {}'.format(name,idx,val))


    def add_checkbox_list(self,txt,choices,attr=None,desc='',indent=1):
        indent *= 20
        self.add_checkbox('Uncheck All',attr='check_toggle')
        cb = CheckedListBox()

        for a,l,t in choices:
            cb.Items.Add(t,True)
            setattr(self,a,True)
            self.inputs.append({
                'type': 'check',
                'label': l,
                'input': t,
                'attr': a,
                'required': False
            })
        
        cb.ItemCheck += ItemCheckEventHandler(self.check_list_handler)
        cb.CheckOnClick = True
        cb.Text = txt
        cb.TextAlign = ContentAlignment.BottomLeft
        cb.Margin = Padding(indent,0,0,0)
        p_size = cb.PreferredSize
        cb.Height = p_size.Height 
        cb.Width = self.get_width(75)
        self.check_list = cb
        self.table.Controls.Add(cb)
        # self.inputs.append({
        #     'type': 'check',
        #     'label': txt,
        #     'input': cb,
        #     'attr': attr,
        #     'required': False
        # })

    def add_patient_input(self):
        panel = TableLayoutPanel()
        panel.ColumnCount = 2
        panel.RowCount = 1
        panel.Padding = Padding(0)
        panel.BackColor = Color.White
        panel.AutoSize = True
        panel.Height = 30
        panel.Anchor = AnchorStyles.Left

        self.add_label('Patient ID (or file of IDs)')
        tb = TextBox()
        tb.Width = 220
        tb.Height = 30
        tb.Margin = Padding(10,0,10,0)
        tb.Text = self.patient_input
        tb.PlaceholderText = 'Patient ID'
        tb.Tag = 'patient_input'
        tb.TextChanged += self.set_attr
        self.patient_input_text = tb
        panel.Controls.Add(self.patient_input_text)

        btn = Button()
        btn.Text = 'Browse'
        btn.Height = 25
        btn.Width = 100
        btn.Margin = Padding(10,0,10,10)
        btn.BackColor = Color.LightGray
        btn.FlatStyle = FlatStyle.Flat
        btn.Click += self.open_file_browser
        panel.Controls.Add(btn)
        self.table.Controls.Add(panel)

        self.inputs.append({
            'type': 'attribute',
            'label': 'Patient ID',
            'input': None,
            'attr': 'patient_input',
            'required': False
        })

    def open_file_browser(self,*args,**kwargs):
        dialog = OpenFileDialog()
        dialog.Filter = 'txt files (*.txt)|*.txt|All files (*.*)|*.*'
        if dialog.ShowDialog() == DialogResult.OK:
            if dialog.FileName: 
                self.patient_input_text.Text = dialog.FileName
                self.patient_input = dialog.FileName
                # self.patient_input_dir.Text = ''
                # self.patient_directory = ''

    def open_dir_browser(self,*args,**kwargs):
        dialog = FolderBrowserDialog()
        dialog.ShowNewFolderButton = False
        # dialog.SelectedPath = self.browse_root
        # dialog.InitialDirectory = self.browse_root

        if dialog.ShowDialog() == DialogResult.OK:
            if dialog.SelectedPath: 
                logging.info(dialog.SelectedPath)
                self.patient_input_dir.Text = dialog.SelectedPath
                self.patient_directory = dialog.SelectedPath
                # self.patient_input_text.Text = ''
                # self.patient_input = ''

    def get_inputs(self):
        results = {}
        for i in self.inputs:
            try:
                item = i['input']
                item_type = i['type']
                label = i['label']
                attr = i['attr']
                reqd = i['required']

                val = ''
                if attr is not None:
                    val = getattr(self,attr)
                elif item_type == 'text':
                    val = self.to_ascii(item.Text)
                elif item_type == 'check':
                    val = [self.to_ascii(v) for v in item if v.Checked]
                elif item_type == 'combo':
                    if item.SelectedIndex >= 0:
                        val = self.to_ascii(item.SelectedItem)
                    elif item.SelectedIndex == -1 and item.Text != '':
                        val = self.to_ascii(item.Text)
                results[label] = {'value':val,'required':reqd}
            except Exception as ex:
                logging.error('Unable to get input value for {}: {}'.format(i['label'],ex))
        return results

    def submit(self,*args,**kwargs):
        vals = self.get_inputs()

        empty_labels = []
        for k,v in vals.items():
            if not v['value']:
                if not v['required']: continue
                if k in self.labels:
                    empty_labels.append(k)
                    self.labels[k].ForeColor = Color.Red

        if empty_labels:
            txt = 'One or more required fields are missing:'
            for e in empty_labels:
                txt += '\n  - {}'.format(e)
            MessageBox.Show(txt,'Required Fields',MessageBoxButtons.OK,MessageBoxIcon.Warning)
            self.status = False
        else:
            self.form.DialogResult = True
            self.status = True

    def cancel(self,*args,**kwargs):
        self.form.DialogResult = True
        self.status = False

    def get_width(self,margin=0):
        return self.form.MaximumSize.Width - margin

    def add_label(self,txt,is_bold=False):
        width = self.get_width(55)
        height = Screen.PrimaryScreen.WorkingArea.Bottom

        label = Label()
        label.Text = txt
        if is_bold: label.Font = Font(label.Font,FontStyle.Bold)
        label.AutoSize = True
        label.MaximumSize = Size(width,height)
        label.Margin = Padding(10,10,10,0)
        self.table.Controls.Add(label)
        self.labels[txt] = label

    def add_textbox(self,txt,attr=None,private=False,required=True):
        self.add_label(txt)
        tb = TextBox()
        tb.Height = 30
        tb.Width = self.get_width(55)
        tb.Margin = Padding(10,0,10,0)
        if attr is not None: 
            tb.Tag = attr
            tb.Text = getattr(self,attr,'')
            tb.TextChanged += self.set_attr 
        if private: tb.UseSystemPasswordChar = True
        self.table.Controls.Add(tb)
        self.inputs.append({
            'type': 'text',
            'label': txt,
            'input': tb,
            'attr': attr,
            'required': required
        })

    def add_combo(self,txt,opts,attr=None,required=True,default=''):
        self.add_label(txt)
        cb = ComboBox()
        cb.Height = 30
        cb.Width = self.get_width(margin=60)
        cb.DropDownStyle = ComboBoxStyle.DropDown
        cb.Items.AddRange(opts)
        if not default: default = opts[0]
        cb.SelectedItem = default
        cb.Margin = Padding(10,0,10,0)
        if attr is not None: 
            setattr(self,attr,default)
            cb.Tag = attr
            cb.TextChanged += self.set_attr
        self.table.Controls.Add(cb)
        self.inputs.append({
            'type': 'combo',
            'label': txt,
            'input': cb,
            'attr': attr,
            'required': required
        })

    def add_checkbox(self,txt,attr=None,checked=True,desc='',indent=1):
        indent *= 20
        # if desc: txt += '\n{}'.format(desc)
        cb = CheckBox()
        cb.Text = txt + desc
        cb.Checked = checked
        cb.TextAlign = ContentAlignment.BottomLeft
        cb.Margin = Padding(indent,0,0,0)
        p_size = cb.PreferredSize
        cb.Height = p_size.Height 
        # if desc: cb.Height += 10
        cb.Width = p_size.Width
        if attr is not None: 
            setattr(self,attr,checked)
            cb.Tag = attr
            cb.CheckedChanged += self.set_attr
            if attr == 'check_toggle': setattr(self,'check_toggle_cb',cb)
        self.table.Controls.Add(cb)
        self.inputs.append({
            'type': 'check',
            'label': txt,
            'input': cb,
            'attr': attr,
            'required': False
        })

    def add_footer_buttons(self):
        panel = TableLayoutPanel()
        panel.ColumnCount = 2
        panel.RowCount = 1
        panel.Padding = Padding(0)
        panel.BackColor = Color.White
        panel.AutoSize = True
        panel.Anchor = AnchorStyles.Right

        btn = Button()
        btn.Text = 'OK'
        btn.Height = 30
        btn.Width = 70
        btn.Margin = Padding(10,10,10,0)
        btn.BackColor = Color.LightGray
        btn.FlatStyle = FlatStyle.Flat
        btn.Click += self.submit
        panel.Controls.Add(btn)

        btn = Button()
        btn.Text = 'Cancel'
        btn.Height = 30
        btn.Width = 70
        btn.Margin = Padding(0,10,10,0)
        btn.BackColor = Color.LightGray
        btn.FlatStyle = FlatStyle.Flat
        btn.Click += self.cancel
        panel.Controls.Add(btn)

        self.table.Controls.Add(panel)

def parse_comments(cmnt):
    project = ''
    subject = ''
    session = ''
    if 'Project:' in cmnt: project = cmnt.split('Project:')[-1].split(' ')[0]
    if 'Subject:' in cmnt: subject = cmnt.split('Subject:')[-1].split(' ')[0]
    if 'Session:' in cmnt: session = cmnt.split('Session:')[-1].split(' ')[0]
    return project,subject,session

def get_comments(case):
    cmnts = case.Comments
    project,subject,session = parse_comments(cmnts)
    if not all([project,subject,session]):
        patient = get_current('Patient')
        cmnts = patient.Comments
        proj,sub,sess = parse_comments(cmnts)
        if not project: project = proj
        if not subject: subject = sub
        if not session: session = sess
    if 'AA:TRUE' not in cmnts: cmnts += ' AA:TRUE'
    return cmnts,project,subject,session

def edit_dicom_tag(path,tag,value):
    try:
        ds = pydicom.dcmread(path)
        try:
            ds[tag] = value
        except:
            ds.add_new(tag,dictionary_VR(tag),value)
        ds.save_as(path)
        return True
    except Exception as ex:
        logging.error('Unable to edit DICOM comments: {}'.format(ex))
    return False

def export_exams(case):
    xnat_host = 'https://xnat.mdanderson.org'
    export_info = {
        'Node':'10.68.11.30',
        'Port':8104,
        'CallingAE':'XNATfromRS',
        'CalledAE':'XNAT'
    }

    # xnat_host = 'https://xnattest.mdanderson.org'
    # export_info = {
    #     'Node':'10.68.2.111',
    #     'Port':8112,
    #     'CallingAE':'XNATfromRS',
    #     'CalledAE':'XNAT_TEST_DA'
    # }

    comments,xnat_project,xnat_subject,xnat_session = get_comments(case)


    if not all([xnat_project,xnat_subject,xnat_session]):
        logging.warning('Unable to export case: Unknown XNAT project/session/scan. The following were found:')
        print(' - XNAT Project: {}'.format('MISSING' if not xnat_project else xnat_project))
        print(' - XNAT Subject: {}'.format('MISSING' if not xnat_subject else xnat_subject))
        print(' - XNAT Session: {}'.format('MISSING' if not xnat_session else xnat_session))
        return

    exports = {}
    for e in case.Examinations:
        name = e.Name
        data = e.GetAcquisitionDataFromDicom()
        desc = str(data['SeriesModule']['SeriesDescription'])
        proto = str(data['SeriesModule']['ProtocolName'])
        series_num = e.GetStoredDicomTagValueForVerification(Group=0x0020,Element=0x0011)
        exports[name] = {'desc':desc,'proto':proto,'series':series_num['Series Number'],'rtss':[]}

    rt_exam_names = []
    for s in case.PatientModel.StructureSets:
        for r in s.RoiGeometries:
            rt_exam = case.Examinations[s.OnExamination.Name].Name
            if not r.HasContours(): continue
            if rt_exam in exports:
                roi_type = ''
                try:
                    roi_type = r.OfRoi.Type
                except: pass
                if not roi_type or roi_type is None: r.OfRoi.Type = 'Undefined'
                print('Found RTSTRUCT for {}: {}'.format(rt_exam,r.OfRoi.Name))
                exports[rt_exam]['rtss'].append([rt_exam,r.OfRoi.Name])
                rt_exam_names.append(rt_exam)

    if not len(exports): 
        print('No exams found. Moving to next case')
        return

    ui = InputUI()
    ui.show_confirmation(exports,case.CaseName)
    if not ui.status: 
        print('Export cancelled.')
        return

    ex_exports = []
    rt_exports = []
    ui_dict = vars(ui)
    for k,v in ui_dict.items():
        if k.startswith('exam_') and v:
            k = k.replace('exam_','')
            if k not in exports: continue
            ex_exports.append(k)
        elif k.startswith('rtss_') and v:
            k = k.replace('rtss_','')
            try:
                if k in rt_exam_names: rt_exports.append(k)
            except: pass

    ex_exports = list(set(ex_exports))
    rt_exports = list(set(rt_exports))
    logging.info('Exams: {}'.format(ex_exports))
    logging.info('RTSSs: {}'.format(rt_exports))

    n_exports = len(ex_exports) + len(rt_exports)
    if not n_exports:
        logging.warning('No exams found for export')
        return

    txt = 'Sending {} series ({} exams and {} RTStructs) to {}'.format(n_exports,len(ex_exports),len(rt_exports),export_info)
    txt += '\nXNAT Destination:'
    txt += '\n  - XNAT Host:    {}'.format(xnat_host)
    txt += '\n  - XNAT Project: {}'.format(xnat_project)
    txt += '\n  - XNAT Subject: {}'.format(xnat_subject)
    txt += '\n  - XNAT Session: {}'.format(xnat_session)
    logging.info(txt)

    xnat = XnatConnection(xnat_host)
    if not xnat.is_connected: return
    if xnat_project: xnat.set_prearchive_code(xnat_project,5)

    case.ScriptableDicomExport(Connection=export_info, Examinations=ex_exports, RtStructureSetsForExaminations=[])

    tmp_dir = os.path.join(r'C:\Temp','exports')
    if os.path.exists(tmp_dir): shutil.rmtree(tmp_dir)

    for r in rt_exports:
        rt_dir = os.path.join(tmp_dir,r.replace(' ','_'))
        if not os.path.exists(rt_dir): os.makedirs(rt_dir)
        logging.info('Saving RTSTRUCT for {} to {}...'.format(r,rt_dir))
        case.ScriptableDicomExport(ExportFolderPath=rt_dir, Examinations=[], RtStructureSetsForExaminations=[r])

        for item in os.scandir(rt_dir):
            if not item.name.startswith('RS'): continue
            logging.info('Uploading {} to XNAT (project: {}, subject: {}, session: {})...'.format(item.path,xnat_project,xnat_subject,xnat_session))
            series_num = exports[r]['series']
            if not edit_dicom_tag(item.path,[0x0010,0x4000],comments): continue
            if not edit_dicom_tag(item.path,[0x0020,0x0011],series_num): continue
            if xnat.gradual_upload(item.path,xnat_project,xnat_subject,xnat_session):
                logging.info('Successfully uploaded RTSTRUCT to {} (series {})'.format(comments.replace(' AA:TRUE',''),series_num))

    if os.path.exists(tmp_dir): shutil.rmtree(tmp_dir)

def format_error(err_str=''):
    try:
        tb = sys.exc_info()[2]
        err_msg = '{}'.format(err_str)
        count = 0
        for exc_tb in traceback.extract_tb(tb):
            count += 1
            fname = exc_tb[0].split('/')[-1]
            line = exc_tb[1]
            func = exc_tb[2]
            err_str = exc_tb[3]
            err_msg += '\n{}-> ({}, {}, line {}): {}'.format('  '*count,fname,func,line,err_str)
    except Exception as ex:
        if not err_str:
            err_msg = 'There was an error trying to parse the original error: {}'.format(ex)
        else:
            err_msg = '{}'.format(err_str)
    logging.error(err_msg)

def main():
    curr_patient = ''
    try:
        patient = get_current('Patient')
        curr_patient = str(patient.PatientID)
        logging.info('Using currently loaded patient: {}'.format(curr_patient))
    except: pass

    ui = InputUI()
    ui.show_import_screen(curr_patient)

    if not ui.status:
        logging.info('Export cancelled.')
        return

    if not ui.patient_input:
        logging.warning('No Patient ID found in input.')
        return
    
    logging.info('PATIENT ID:   {}'.format(ui.patient_input))

    #Load patient data
    pl = PatientLoader(ui.patient_input)
    if not len(pl.patients): return

    logging.info('Number of patients found: {}'.format(len(pl.patients)))
    patient_list = []
    for pid in pl.patients:
        if pid != curr_patient:
            if not pl.load_patient(pid): continue
            patient = get_current('Patient')
            curr_patient = str(patient.PatientID)
            for case in patient.Cases:
              exports = {} 
              for e in case.Examinations:
                name = e.Name
                data = e.GetAcquisitionDataFromDicom()
                # AX LAVA Description
                desc = str(data['SeriesModule']['SeriesDescription'])
                proto = str(data['SeriesModule']['ProtocolName'])
                desc = desc.replace("/", "_")
                desc = desc.replace(" ", "_")   
                desc = desc.replace(":", "_")
                desc = desc.replace("&", "and")
                case_nam = case.CaseName
                case_nam = case_nam.replace(" ", "_")
                series_num = e.GetStoredDicomTagValueForVerification(Group=0x0020,Element=0x0011)
                exports[name] = {'exam':e, 'name': name, 'desc':desc,'proto':proto,'series':series_num['Series Number'],'rtss':[]}
		            
                #logging.info("export data: {}".format({'name':name, 'desc':desc,'proto':proto,'series':series_num['Series Number'],'rtss':[]}))
                # add on the rt struct to the correct dicom images
              rt_exam_names = []
              for s in case.PatientModel.StructureSets:
                for r in s.RoiGeometries:
                  rt_exam = case.Examinations[s.OnExamination.Name].Name
                  if not r.HasContours(): continue
                  if rt_exam in exports:
                    roi_type = ''
                    try:
                      roi_type = r.OfRoi.Type
                    except: pass
                    if not roi_type or roi_type is None: r.OfRoi.Type = 'Undefined'
                    #logging.info('Found RTSTRUCT for {}: {}'.format(rt_exam,r.OfRoi.Name))
                    exports[rt_exam]['rtss'].append([rt_exam,r.OfRoi.Name])
                    rt_exam_names.append(rt_exam)
              ui = InputUI()
              logging.info('--------------')
              logging.info('Using currently loaded patient: {}'.format(curr_patient))
              logging.info("patient exports:: {}".format(str(exports)))
              logging.info('--------------')
		
              logging.info('check patient'.format(str(patient.PatientID)))
              #ui.show_confirmation(curr_patient,exports,case.CaseName) 
	           	
              logging.info("before export")  
              for dicoms in exports.keys():
                item = exports[dicoms]
                logging.info('item: {}'.format(str(item)))
                desc = item['desc']
                #logging.info('desc {}'.format(desc))
		        
		
                patient_folder = export_folder + '/' + patient.Name
                if not os.path.exists(patient_folder): mkdir(patient_folder)
		         
                scan_folder = patient_folder + '/' + desc + "_" + case_nam
					
                if not os.path.exists(patient_folder): mkdir(scan_folder)
		
                #tmp_dir = os.path.join(r'C:\Temp','exports')
                #if os.path.exists(tmp_dir): shutil.rmtree(tmp_dir)
		
                #Save RT STruct images
                #for r in item['rtss']:
                #  r = r[0]
                #  logging.info("r: {}".format(r))
		        #      
                #  rt_dir = os.path.join(scan_folder,r.replace(' ','_'))
                #  if not os.path.exists(rt_dir): os.makedirs(rt_dir)
                #  logging.info('Saving RTSTRUCT for {} to {}...'.format(r,rt_dir))
                #  case.ScriptableDicomExport(ExportFolderPath=rt_dir, Examinations=[], RtStructureSetsForExaminations=[r])
		          
                # Save Dicom images
                case_path = os.path.join(scan_folder, 'dicom' + item['name'].replace(' ' , ''))
                if not os.path.exists(case_path): os.makedirs(case_path)
                case.ScriptableDicomExport(
		              ExportFolderPath = case_path,
		              Examinations = [item['name']],
		              RtStructureSetsForExaminations = [item['name']],
		              IgnorePreConditionWarnings = True
                )
                patient_list.append([curr_patient,case_nam,e, desc,proto,series_num['Series Number'], item['rtss']])

    logging.info('Done!')
    df = pd.DataFrame(data=patient_list,columns = ['patientID', 'case', 'e', 'desc','proto','Series Number', 'rtss'])
    df.to_csv(export_folder +'\\patient_list.csv') 

if __name__ == '__main__':
    main()
