import os
import time
import yaml
import json
import datetime
import numpy as np
import pandas as pd
from time import strftime
from pprint import pprint
import matplotlib.pyplot as plt

from diffpy.Structure import loadStructure
from diffpy.Structure import StructureFormatError
from diffpy.srreal.structureadapter import nosymmetry
from diffpy.srreal.pdfcalculator import DebyePDFCalculator
from diffpy.srreal.pdfcalculator import PDFCalculator

from pymatgen.io.cif import CifParser
from pymatgen.analysis.diffraction.xrd import XRDCalculator

from .glbl import pdfCal_cfg, Uiso

def _makedirs(path_name):
    '''function to support python2 stupid logic'''
    if os.path.isdir(path_name):
        pass
    else:
        os.makedirs(path_name)


def _timestampstr(timestamp):
    ''' convert timestamp to strftime formate '''
    timestring = datetime.datetime.fromtimestamp(\
                 float(timestamp)).strftime('%Y%m%d-%H%M')
    return timestring

def find_nearest(std_array, val):
    """function to find the index of nearest value"""
    idx = (np.abs(std_array-val)).argmin()
    return idx

def theta2q(theta, wavelength):
    """transform from 2theta to Q(A^-1)"""
    _theta = theta.astype(float)
    rad = np.deg2rad(_theta)
    q = 4*np.pi/wavelength*np.sin(rad/2)
    return q

def assign_nearest(std_array, q_array, iq_val):
    """assign value to nearest grid"""
    idx_list = []
    interp_iq = np.zeros_like(std_array)
    for val in q_array:
        idx_list.append(find_nearest(std_array, val))
    interp_iq[idx_list]=iq_val
    return interp_iq

calculate_params = {}

wavelength = 0.5
tth_range = np.arange(0, 90, 0.1)
std_q = theta2q(tth_range, wavelength)

####### configure pymatgen XRD calculator #####
# instantiate calculators
xrd_cal = XRDCalculator()
xrd_cal.wavelength = wavelength
xrd_cal.TWO_THETA_TOL = 10**-2
calculate_params.update({'xrd_wavelength':
                         xrd_cal.wavelength})

####### configure diffpy PDF calculator ######
cal = PDFCalculator()

def map_learninglib(cif_list, xrd=False):
    """function designed for parallel computation

    Parameters
    ----------
    cif_list : list
        List of cif filenames
    xrd : bool, optional
        Wether to calculate xrd pattern. Default to False
    """
    _cif = cif_list
    sg_list = []
    fail_list = []
    xrd_list = []
    struc_df = pd.DataFrame()
    composition_list_1 = []
    composition_list_2 = []
    try:
        # diffpy structure
        struc = loadStructure(_cif)
        struc.Uisoequiv = Uiso
        print('pass struc load')

        ## calculate PDF/RDF with diffpy ##
        r_grid, gr = cal(struc, **pdfCal_cfg)
        density = cal.slope
        print('pass diffpy')

        # pymatgen structure
        struc_meta = CifParser(_cif)
        ## calculate XRD with pymatgen ##
        if xrd:
            xrd = xrd_cal.get_xrd_data(struc_meta\
                    .get_structures(False).pop())
            _xrd = np.asarray(xrd)[:,:2]
            q, iq = _xrd.T
            q = theta2q(q, wavelength)
            interp_q = assign_nearest(std_q, q, iq)
            xrd_list.append(interp_q)
        else:
            pass
        ## test if space group info can be parsed##
        dummy_struc = struc_meta.get_structures(False).pop()
        _sg = dummy_struc.get_space_group_info()
        print('pass struc info')
    except:
        print("{} fail".format(_cif))
        fail_list.append(_cif)
        # parallelized so direct return
        return fail_list
    else:
        # no error for both pymatgen and diffpy
        #gr = cal.pdf
        #rdf = cal.rdf
        #density = cal.slope
        print('=== Finished evaluating PDF from structure {} ==='
               .format(_cif))

        ## update features ##
        flag = ['primitive', 'ordinary']
        option = [True, False]
        compo_list = [composition_list_1, composition_list_2]
        struc_fields = ['a','b','c','alpha','beta','gamma',
                        'volume', 'sg_label', 'sg_order']
        rv_dict = {}
        for f, op, compo in zip(flag, option, compo_list):
            struc = struc_meta.get_structures(op).pop()
            a, b, c = struc.lattice.abc
            aa, bb, cc = struc.lattice.angles
            volume = struc.volume
            sg, sg_order = struc.get_space_group_info()
            for k, v in zip(struc_fields,
                            [a, b, c, aa, bb, cc, volume,
                             sg, sg_order]):
                rv_dict.update({"{}_{}".format(f, k) : v})
            compo.append(struc.composition.as_dict())
        struc_df = struc_df.append(rv_dict, ignore_index=True)

        # print('=== Finished evaluating XRD from structure {} ==='
        #       .format(_cif))
        rv_name_list = ['gr', 'density', 'r_grid',
                        'xrd_info', 'q_grid',
                        'primitive_composition_list',
                        'ordinary_composition_list',
                        'struc_df', 'fail_list']
        xrd_info = np.asarray(xrd_list)
        q_grid = std_q
        print('{:=^80}'.format(' Return '))
        print('\n'.join(rv_name_list))

        return (gr, density, r_grid, xrd_info, q_grid,
                composition_list_1, composition_list_2,
                struc_df, fail_list)


def learninglib_build(cif_list, xrd=False):
    """function designed for parallel computation

    Parameters
    ----------
    cif_list : list
        List of cif filenames
    xrd : bool, optional
        Wether to calculate xrd pattern. Default to False
    """
    gr_list = []
    density_list = []
    xrd_list = []
    struc_df = pd.DataFrame()
    fail_list = []
    composition_list_1 = []
    composition_list_2 = []

    # database fields
    flag = ['primitive', 'ordinary']
    option = [True, False]
    compo_list = [composition_list_1, composition_list_2]
    struc_fields = ['a','b','c','alpha','beta','gamma',
                    'volume', 'sg_label', 'sg_order']
    # looping
    for _cif in sorted(cif_list):
        try:
            # diffpy structure
            struc = loadStructure(_cif)
            struc.Uisoequiv = Uiso

            ## calculate PDF/RDF with diffpy ##
            r_grid, gr = cal(struc, **pdfCal_cfg)
            density = cal.slope

            # pymatgen structure
            struc_meta = CifParser(_cif)
            ## calculate XRD with pymatgen ##
            if xrd:
                xrd = xrd_cal.get_xrd_data(struc_meta\
                        .get_structures(False).pop())
                _xrd = np.asarray(xrd)[:,:2]
                q, iq = _xrd.T
                q = theta2q(q, wavelength)
                interp_q = assign_nearest(std_q, q, iq)
                xrd_list.append(interp_q)
            else:
                pass
            ## test if space group info can be parsed##
            dummy_struc = struc_meta.get_structures(False).pop()
            _sg = dummy_struc.get_space_group_info()
        #except RuntimeError:  # allow exception to debug
        except:
            print("{} fail".format(_cif))
            fail_list.append(_cif)
        else:
            # no error for both pymatgen and diffpy
            print('=== Finished evaluating PDF from structure {} ==='
                   .format(_cif))
            ## update features ##
            rv_dict = {}
            for f, op, compo in zip(flag, option, compo_list):
                struc = struc_meta.get_structures(op).pop()
                a, b, c = struc.lattice.abc
                aa, bb, cc = struc.lattice.angles
                volume = struc.volume
                sg, sg_order = struc.get_space_group_info()
                for k, v in zip(struc_fields,
                                [a, b, c, aa, bb, cc, volume,
                                 sg, sg_order]):
                    rv_dict.update({"{}_{}".format(f, k) : v})
                compo.append(struc.composition.as_dict())
            struc_df = struc_df.append(rv_dict, ignore_index=True)

            # storing results
            gr_list.append(gr)
            density_list.append(density)

    # end of loop, storing turn result into ndarray
    r_grid = cal.rgrid
    gr_array = np.asarray(gr_list)
    density_array = np.asarray(density_list)
    xrd_info = np.asarray(xrd_list)
    q_grid = std_q

    # talktive statement
    rv_name_list = ['gr_array', 'density_array', 'r_grid',
                    'xrd_info', 'q_grid',
                    'primitive_composition_list',
                    'ordinary_composition_list',
                    'struc_df', 'fail_list']
    print('{:=^80}'.format(' Return '))
    print('\n'.join(rv_name_list))

    rv = gr_array, density_array, r_grid, xrd_info, q_grid,\
         composition_list_1, composition_list_2, struc_df, fail_list

    return rv

def save_data(output, output_dir=None):
    """function should be called with learninglib_build"""
    timestr = _timestampstr(time.time())
    if output_dir is None:
        tail = "LearningLib_{}".format(timestr)
        output_dir = os.path.join(os.getcwd(), tail)
    os.makedirs(output_dir)
    print('=== output dir would be {} ==='.format(output_dir))
    f_name_list = ['Gr.npy', 'density.npy', 'r_grid.npy',
                   'xrd_info.npy', 'primitive_composition.json',
                   'ordinary_composition.json', 'struc_df.json',
                   'fail_list.json']
    for el, f_name in zip(output, f_name_list):
        w_name = os.path.join(output_dir, f_name)
        if f_name.endswith('.npy'):
            np.save(w_name, el)
        elif f_name.endswith('.json'):
            with open(w_name, 'w') as f:
                json.dump(el, f)
        print("INFO: saved {}".format(w_name))
