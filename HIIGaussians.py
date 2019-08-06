#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Wed May 08 15:35:43 2019

@author: Xavier Jimenez
"""


"""
Silly modification by S.F.Sanchez & C. Espinosa. 19.07.2019
"""

import sys


import itertools
import time
import numpy as np
import os
import scipy
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter
import astropy.units as u
from mpdaf.obj import WCS
from mpdaf.drs import PixTable
from mpdaf.obj import Spectrum, WaveCoord
from mpdaf.sdetect import Catalog
import matplotlib.colors as mcol
from scipy.optimize import curve_fit
import matplotlib.mlab as mlab
from astropy.table import Table
from astropy.cosmology import WMAP9 as cosmo

from mpdaf.obj import Image, Gauss2D, gauss_image, Cube, Moffat2D, moffat_image
from numpy import ma

from astropy.io import fits
from astropy.stats import gaussian_sigma_to_fwhm, gaussian_fwhm_to_sigma
from matplotlib.path import Path
from scipy import interpolate, signal
from scipy import ndimage as ndi
from scipy.ndimage.interpolation import affine_transform
from scipy.optimize import leastsq
from six.moves import range, zip

import HII_MUSE_TESTER as HII_flux

# Defining paths

default_MD_PATH = 'C:/Users/Xavier/Desktop/Stage_UNAM/'
default_OT_PATH = 'C:/Users/Xavier/Desktop/Stage_UNAM/Rapport/Table/'
default_OI_PATH = 'C:/Users/Xavier/Desktop/stage_unam/rapport/'

MUSE_DATA_PATH = os.getenv('MUSE_DATA_PATH', default=default_MD_PATH)
OUTPUT_TABLES_PATH = os.getenv('MT_OUTPUT_PATH', default=default_OT_PATH)
OUTPUT_IMAGES_PATH = os.getenv('MI_OUTPUT_PATH', default=default_OI_PATH)

# def is_max(i,j,ima,ip=-1,jp=-1,frac_peak = 0.15):
#     """Calculate if a point i, j is a maximum.
#
#     Parameters
#     ----------
#     i : int
#         x coordinate of current pixel
#     j : int
#         y coordinate of current pixel
#     ima : numpy narray
#         data map
#     ip : int
#         x coordinate of the current peak pixel
#     jp :int
#         y coordinate of the current peak pixel
#     frac_peak : float
#         Relative threshold with respect to the peak emission of the minimum
#         intensity
#
#     Returns
#     -------
#     int
#         1 larger than nearby, 0 equal, -1 smaller than nearby.


def data2FITS(cube, data, name_file):
    new_header = cube.data_header.copy()
    for label in cube.data_header.keys():
        if label.startswith('NAME'):
            if not label == 'NAME20':
                new_header.remove(label)
    new_header.rename_keyword('NAME20', 'NAME0')
    new_header.remove('NAXIS3')
    new_header.remove('CTYPE3')
    new_header.remove('CUNIT3')
    new_header.remove('CRPIX3')
    new_header.remove('CRVAL3')
    new_header.remove('CRDER3') #KeyError: "Keyword 'CRDER3' not found."
    new_header.remove('CDELT3')
    new_header.update({'NAXIS': 2})
    new_data = np.where(data.mask, np.nan, data)
    hdu = fits.PrimaryHDU(new_data)
    hdu.header = new_header
    hdul = fits.HDUList([hdu])
    hdul.writeto(OUTPUT_TABLES_PATH + name_file, overwrite=True)


def is_near(p, IP, JP, ima, R):
    map_data = ima.data
    L = []
    if p < len(IP):
        i = int(IP[p])
        j = int(JP[p])
        for k in range(i-R, i+R+1):
            for l in range(j-R, j+R+1):
                for n in range(0, len(IP)):
                    if int(IP[n]) == k and int(JP[n]) == l:
                        if map_data[j, i] > map_data[int(JP[n]), int(IP[n])]:
                            L.append(n)
                        if map_data[j, i] < map_data[int(JP[n]), int(IP[n])]:
                            L.append(p)
    # l = set(L)
    # H = list(l)
    IP = np.delete(IP, L)
    JP = np.delete(JP, L)

    return IP, JP
    

def max_coord(ima, name, F_min=0.0):
    imacopy = ima.copy()
#    print("F_min="+str(F_min))
    if F_min == 0.0:
        F_min = flux_min(ima, name)
#    print("F_min="+str(F_min))
    R = 10  # peak radius in pixels
    frac_peak = 0.15
    map_data_now = imacopy.data
    maxindex = map_data_now.argmax()
    fmax = np.amax(map_data_now)
    ip = -1
    jp = -1
    IP = np.array([])
    JP = np.array([])
    is_max1 = 0
    N = 0
    h = 0
    H, L, K = [], [], []
    h, l = 0, 0
    map_data = ima.data
    nx = len(map_data[0])
    ny = len(map_data)
    while fmax > F_min:
        jp = maxindex//nx
        ip = maxindex % nx
        IP = np.append(IP, ip)
        JP = np.append(JP, jp)
        imacopy.mask_ellipse(center=(jp, ip), radius=(R, R), posangle=0,
                             unit_center=None, unit_radius=None)
        map_data_now = imacopy.data
        maxindex = map_data_now.argmax()
        fmax = np.amax(map_data_now)

    # for p in range(0, len(IP)):
    #     IP, JP = is_near(p, IP, JP, ima, R=4)

    # for i in range(0, len(IP)):
    #     for j in range(0, len(JP)):
    #         if (np.abs(IP[i]-IP[j]) < 4.0) and (np.abs(JP[i]-JP[j]) < 4.0) and (i != j):
    #             if map_data[int(JP[i]), int(IP[i])] > map_data[int(JP[j]), int(IP[j])]:
    #                 K.append(j)
    #             else:
    #                 K.append(i)
    # M = set(K)
    # N = list(M)
    # IP = np.delete(IP, N)
    # JP = np.delete(JP, N)

    return IP, JP


def circularity(a, b):
    if b > a:
        return 1-(a/b)
    else:
        return 1-(b/a)


def continuum(ima, JP, IP, cont):
    (n, m) = np.shape(ima)
    int_cont = []

    zeros = np.zeros_like(ima.data)
    for k in range(0, len(cont)):
        int_cont = []
        for i in range(0, n):
            for j in range(0, m):
                if (i == int(JP[k])) and (j == int(IP[k])):
                    int_cont.append(cont[k])

                else:
                    int_cont.append(0.0)
        int_cont_arr = np.array(int_cont)
        int_cont = int_cont_arr.reshape((n, m))
        zeros = zeros + int_cont
    return zeros

def background_interpolation(ima, name, F_min=0):
    if F_min == 0:
        fmin = 0
        F_min = flux_min(ima, name)
    else:
        fmin = F_min
    (h, w) = np.shape(ima)
    IP2, JP2 = [], []
    tcont = []
    map_data = ima.data
    for i in range(0, h, 2):
        for j in range(0, w, 2):
            if map_data[i][j] < F_min:
                JP2.append(i)
                IP2.append(j)
                # tcont.append(map_data[i][j])
                tcont.append(0.0)
    return JP2, IP2, tcont

def interpolate_continuum(ima, JP, IP, I, J, pcont, cont, JP3, IP3, tcont, plot=False, F_min=0):
    (h, w) = np.shape(ima)
    coords = []
    map_data = ima.data
    for i in range(0, len(IP)):
        if cont[i] > 0:
            IP3.append(int(IP[i]))
            JP3.append(int(JP[i]))
            tcont.append(cont[i])
    for i in range(0, len(I)):
        if pcont[i] > 0:
            IP3.append(int(I[i]))
            JP3.append(int(J[i]))
            tcont.append(pcont[i])
    (n, m, l, k) = (np.amax(IP3), np.amax(JP3), np.amin(IP3), np.amin(JP3))

    x = np.linspace(0, h-1, h)
    y = np.linspace(0, w-1, w)
    X, Y = np.meshgrid(x, y)
    grid_z0 = interpolate.griddata((JP3, IP3), np.array(tcont), (X, Y),
                                   method='nearest')
    # plt.imshow(grid_z0.T, origin='lower')
    grid = Image(data=(grid_z0.T), wcs=ima.wcs)
    grid.gaussian_filter(sigma=5, inplace=True)
    if plot:
        fig = plt.figure()
        grid.plot(scale='log', vmin=0, vmax=np.amax(ima.data), colorbar='v')
    return grid


def HIIplot_cont(gfitim, grid, ima):
    return Image(data=(gfitim.data + grid.data), wcs=ima.wcs)


def gaussian_2dc(xy_mesh, amp, xc, yc, sigma, cont):
    (x, y) = xy_mesh
    gauss = amp*np.exp(-((x-xc)**2/(2*sigma**2)+(y-yc)**2/(2*sigma**2)))/(2*np.pi*sigma*sigma) + cont
    return gauss


def gaussian_2d(xy_mesh, amp, xc, yc, sigma):
    (x, y) = xy_mesh
    gauss = amp*np.exp(-((x-xc)**2/(2*sigma**2)+(y-yc)**2/(2*sigma**2)))/(2*np.pi*sigma*sigma)
    return gauss


def bimodal_gaussian_2d(xy_mesh, *p):
    amp1, xc1, yc1, sigma1, amp2, xc2, yc2, sigma2, cont = p
    return gaussian_2d(xy_mesh, amp1, xc1, yc1, sigma1) + gaussian_2d(xy_mesh, amp2, xc2, yc2, sigma2) + cont


def trimodal_gaussian_2d(xy_mesh, *p):
    amp1, xc1, yc1, sigma1, amp2, xc2, yc2, sigma2, amp3, xc3, yc3, sigma3, cont = p
    return gaussian_2d(xy_mesh, amp1, xc1, yc1, sigma1) + gaussian_2d(xy_mesh, amp2, xc2, yc2, sigma2) + gaussian_2d(xy_mesh, amp3, xc3, yc3, sigma3) + cont


def gaussian_2dc_ravel(xy_mesh, amp, xc, yc, sigma, cont):
    return np.ravel(gaussian_2dc(xy_mesh, amp, xc, yc, sigma, cont))


def gaussian_2d_ravel(xy_mesh, amp, xc, yc, sigma):
    return np.ravel(gaussian_2d(xy_mesh, amp, xc, yc, sigma))


def bimodal_gaussian_2d_ravel(xy_mesh, *p):
    amp1, xc1, yc1, sigma1, amp2, xc2, yc2, sigma2, cont = p
    return gaussian_2d_ravel(xy_mesh, amp1, xc1, yc1, sigma1) + gaussian_2d_ravel(xy_mesh, amp2, xc2, yc2, sigma2) + cont


def trimodal_gaussian_2d_ravel(xy_mesh, *p):
    amp1, xc1, yc1, sigma1, amp2, xc2, yc2, sigma2, amp3, xc3, yc3, sigma3, cont = p
    return gaussian_2d_ravel(xy_mesh, amp1, xc1, yc1, sigma1) + gaussian_2d_ravel(xy_mesh, amp2, xc2, yc2, sigma2) + gaussian_2d_ravel(xy_mesh, amp3, xc3, yc3, sigma3) + cont


def dual_gauss2D_fit(ima, subima, subima_err, center):
    (n, m) = np.shape(subima)
    N = n
    data = subima.data
    imax = data.argmax()
    jp = imax//n
    ip = imax % m
    data = subima.data.compressed()
    # center = [jp, ip]
    center = center
    width = subima.moments(unit=None)
    fwhm = width * gaussian_sigma_to_fwhm
    cont = 0.0
    peak = subima._data[int(center[0]), int(center[1])] - cont

    # two gaussians parameters
    xc1, yc1 = center[0], center[1]
    xc2, yc2 = center[0], center[1]
    sigma1, sigma2 = 1.2*fwhm[0], 0.8*fwhm[0]
    A1 = 1*peak*2*np.pi*sigma1*sigma1
    A2 = 0.5*peak*2*np.pi*sigma2*sigma2

    cont = 0.1

    x = np.linspace(0, N, N)
    y = np.linspace(0, N, N)

    xy_mesh = np.meshgrid(x, y)

    z = bimodal_gaussian_2d(xy_mesh,
                            A1, xc1, yc1, sigma1,
                            A2, xc2, yc2, sigma2, cont)

    z_noisy = subima.data

    guess_values = [A1, xc1, yc1, sigma1, A2, xc2, yc2, sigma2, cont]

    coeff, cov_mat = curve_fit(bimodal_gaussian_2d_ravel, xy_mesh,
                               np.ravel(z_noisy), p0=guess_values,
                               sigma=np.ravel(subima_err.data))

    fit_errors = np.sqrt(np.diag(cov_mat))
    fit_residual = z_noisy - bimodal_gaussian_2d(xy_mesh, *coeff).reshape(np.outer(x, y).shape)
    fit_Rsquared = 1 - np.var(fit_residual)/np.var(z_noisy)

    return xy_mesh, [coeff[0], coeff[1], coeff[2], coeff[3], coeff[4], coeff[5], coeff[6], coeff[7], coeff[8]], [fit_errors[0], fit_errors[1], fit_errors[2], fit_errors[3], fit_errors[4], fit_errors[5], fit_errors[6], fit_errors[7], fit_errors[8]]


def gauss2D_fit(ima, subima, subima_err, center):

    # subima.peak()
    # subima.fwhm()
    (n, m) = np.shape(subima)
    N = n
    data = subima.data
    imax = data.argmax()
    jp = imax//n
    ip = imax%m
    data = subima.data.compressed()
    center = [jp, ip]
    # center=center
    width = subima.moments(unit=None)
    fwhm = width * gaussian_sigma_to_fwhm
    cont = 0.0
    peak = subima._data[int(center[0]), int(center[1])] - cont


    # two gaussians parameters
    xc1, yc1 =center[0], center[1]
    sigma1 = 0.5*fwhm[0]
    A1 = 0.7*peak*2*np.pi*sigma1*sigma1

    cont = 0.1

    x = np.linspace(0, N, N)
    y = np.linspace(0, N, N)

    xy_mesh = np.meshgrid(x, y)


    z = gaussian_2dc(xy_mesh, A1, xc1, yc1, sigma1, cont)

    z_noisy = subima.data

    guess_values = [A1, xc1, yc1, sigma1, cont]

    coeff, cov_mat = curve_fit(gaussian_2dc_ravel, xy_mesh, np.ravel(z_noisy), p0=guess_values, sigma = np.ravel(subima_err.data))


    fit_errors = np.sqrt(np.diag(cov_mat))
    fit_residual = z_noisy - gaussian_2dc(xy_mesh, *coeff).reshape(np.outer(x,y).shape)
    fit_Rsquared = 1 - np.var(fit_residual)/np.var(z_noisy)

    return xy_mesh, [coeff[0],coeff[1],coeff[2],coeff[3],coeff[4]], [fit_errors[0],fit_errors[1],fit_errors[2],fit_errors[3],fit_errors[4]]


def sub2center(x, y, ima, subima):
    subcenter = subima.wcs.pix2sky([x, y])
    center = ima.wcs.sky2pix([subcenter[0][0], subcenter[0][1]])
    return center[0][0], center[0][1]

def center2sub(x, y, ima, subima):
    center = ima.wcs.pix2sky([x, y])
    subcenter = subima.wcs.sky2pix([center[0][0], center[0][1]])
    return subcenter[0][0], subcenter[0][1]

def sky2center(x, y, ima):
    gcenter = ima.wcs.sky2pix([x, y])
    return gcenter[0][0], gcenter[0][1]

def center2sky(x, y, ima):
    gcenter = ima.wcs.pix2sky([x, y])
    return gcenter[0][0], gcenter[0][1]


def HIIrecover_loop(ima, ima_err, name, plot=False, p=0, F_min=0):
    if F_min == 0:
        fmin = 0
        F_min = flux_min(ima, name)
    else:
        fmin = F_min
    IP, JP = max_coord(ima, name, 0.0)
    IP2,JP2 = [], []
    (n, m) = np.shape(ima)
    l = 17 #default box size
    cont = []
    I, J = [], []
    h = 0
    H = []
    K = []
    gauss_param = []
    counter = 0
    map_data=ima.data
    IPd = []
    JPd = []
    IPs = []
    JPs = []
    chi2_basicfit, chi2_dualfit, chi2_gfit, chi2, parameter = 0, 0, 0, 0, 0
    alpha_list = []
    for i in range(0, len(IP)):
        ip, jp = IP[i], JP[i]
        subima = ima.subimage(center=(jp,ip), size=(l,l), unit_center=None, unit_size=None)
        k = box_size(ima, subima)
        k=15
        subima = ima.subimage(center=(jp,ip), size=(k,k), unit_center=None, unit_size=None)
        subima_err = ima_err.subimage(center=(jp,ip), size=(k,k), unit_center=None, unit_size=None)
        subima_err = error_ponderation(subima_err)
        size=np.shape(subima)
        center = center2sub(x=jp, y=ip, ima=ima, subima=subima)


        subima.unmask()
        subima.mask_region(center=[(size[0]//2)-1,(size[1]//2)-1], radius=k//2, unit_center=None, unit_radius=None, inside=False)

        try:
            xy_mesh, coeff, fit_errors = gauss2D_fit(ima, subima, subima_err, center)
            try:
                gfitim = gaussian_2dc(xy_mesh, coeff[0],coeff[1],coeff[2],coeff[3],coeff[4])
            except:
                print('gaussian fit failed')
            parameter=4
            chi2_basicfit = chi_square(subima, subima_err, gfitim, parameter)
            alpha = 0
            alpha_list.append(alpha)
    
#            if (coeff[0] > F_min) and (fit_errors[3] < 0.08*coeff[3]) and (((size[0]/2-coeff[1])**2 + (size[1]/2-coeff[2])**2)**0.5 < 3) and (coeff[3] < redshift(name)) and (coeff[3]>0.5):
            if (coeff[0] > F_min) and (fit_errors[3] < 0.08*coeff[3]) and (((size[0]/2-coeff[1])**2 + (size[1]/2-coeff[2])**2)**0.5 < 3) and (coeff[3] < scale_based_on_redshift(redshift_input)) and (coeff[3]>0.5):
                gfitim = gaussian_2dc(xy_mesh, coeff[0],coeff[1],coeff[2],coeff[3],coeff[4])
                center = sub2center(coeff[1], coeff[2], ima, subima)
                if plot == True:
                    fig, ax = plt.subplots(1, 4, figsize=(16, 4), tight_layout=True)
                    counter+=1
                    gfitim = gaussian_2dc(xy_mesh, coeff[0],coeff[1],coeff[2],coeff[3],coeff[4])
                    gfitim = Image(data=gfitim, wcs=subima.wcs)
                    gfitim.plot(ax=ax[1], colorbar='v', vmax=np.amax(subima.data), title = r'Simple Gauss2D FIT - flux = %s [10$^{-20}$ cgs]'%round(np.sum(gfitim.data),2))
                    subima.plot(colorbar='v', ax=ax[0], vmin=0, zscale=False, title = 'HII number %s' %(counter))
                    res = Image(data=(subima.data - gfitim.data), wcs=subima.wcs)
                    res.plot(ax=ax[2],vmin=0, vmax=np.amax(subima.data), colorbar='v', title = r'Residuals - flux = %s [10$^{-20}$ cgs]'%round(np.sum(res.data),2))
                    res.plot(ax=ax[3],vmin=-F_min, vmax=F_min, colorbar='v', title = r'Residuals - flux = %s [10$^{-20}$ cgs]'%round(np.sum(res.data),2))
                    plt.savefig(OUTPUT_IMAGES_PATH+'gaussfit{}/gfit_num_{}.png'.format(p,counter), bbox_inches='tight', transparent=True)
                    plt.close()
                if (center[0] < n) and (center[1] < m) and (center[0] > 0) and (center[1] > 0):
                    JP2.append(center[0])
                    IP2.append(center[1])
                    JPs.append(center[0])
                    IPs.append(center[1])
                    gauss_param.append([center[0], center[1], coeff[3], coeff[3], map_data[int(center[0])][int(center[1])], 0.0, coeff[4], coeff[0], 0, chi2_basicfit,k, F_min])
                    J.append(center[0]+l)
                    I.append(center[1]+l)
                    J.append(center[0]+l)
                    I.append(center[1]-l)
                    J.append(center[0]-l)
                    I.append(center[1]-l)
                    J.append(center[0]-l)
                    I.append(center[1]+l)
                    cont.append(coeff[4])
                    cont.append(coeff[4])
                    cont.append(coeff[4])
                    cont.append(coeff[4])

        except:
            chi2_basicfit = 10

        


    # plt.figure()
    # plt.hist(alpha_list, color='darkmagenta')



    return IP2, JP2, gauss_param, I, J, cont, IPd, JPd, IPs, JPs



def HIIplot2(IPs, JPs, gauss_im, ima, param=False):
    map_gfitim = np.zeros_like(ima)
    (n,m) = np.shape(ima)
    cont = []
    x = np.linspace(0, m, m)
    y = np.linspace(0, n, n)
    xy_mesh = np.meshgrid(x, y)
    two_fits = 0
    if param == False:
        I1,I2,xc1,yc1,xc2,yc2,sigma1,sigma2,k,chi2,size,alpha,flux = [],[],[],[],[],[],[],[],[],[],[],[],[]
    else:
        I1,I2,xc1,yc1,xc2,yc2,sigma1,sigma2,k,chi2,size,alpha,flux = param


    gfitim = gaussian_2dc(xy_mesh, gauss_im[0][7],gauss_im[0][1],gauss_im[0][0],gauss_im[0][2],0.0)
    I1.append(gauss_im[0][7])
    I2.append(0.0)
    xc1.append(gauss_im[0][1])
    yc1.append(gauss_im[0][0])
    xc2.append(0.0)
    yc2.append(0.0)
    sigma1.append(gauss_im[0][2])
    sigma2.append(0.0)
    k.append(gauss_im[0][6])
    chi2.append(gauss_im[0][9])
    size.append(gauss_im[0][10])
    alpha.append(gauss_im[0][8])
    flux.append(gauss_im[0][11])
    cont.append(gauss_im[0][6])
    for i in range(1, len(gauss_im)):
        gfitim = gfitim + gaussian_2dc(xy_mesh, gauss_im[i][7],gauss_im[i][1],gauss_im[i][0],gauss_im[i][2],0.0)
        I1.append(gauss_im[i][7])
        I2.append(0.0)
        xc1.append(gauss_im[i][1])
        yc1.append(gauss_im[i][0])
        xc2.append(0.0)
        yc2.append(0.0)
        sigma1.append(gauss_im[i][2])
        sigma2.append(0.0)
        k.append(gauss_im[i][6])
        chi2.append(gauss_im[i][9])
        size.append(gauss_im[i][10])
        alpha.append(gauss_im[i][8])
        flux.append(gauss_im[i][11])
        cont.append(gauss_im[i][6])
    # gfitim.plot(ax=ax, scale='log', colorbar='v')
    param = I1,I2,xc1,yc1,xc2,yc2,sigma1,sigma2,k,chi2,size,alpha,flux
    return gfitim, cont, param






def loop2(IP2, JP2, I2, J2, pcont2, cont2, gfitim, gfitim2, ima, ima_err, IPd, JPd, param, JP3, IP3, tcont, name, plot=False, F_min=0):
    IPd_list, JPd_list = IPd, JPd
    if F_min == 0:
        F_min = flux_min(ima, name)
    else:
        fmin = F_min
    gfitim_tot = gfitim
    res = Image(data=(ima.data - gfitim.data), wcs=ima.wcs)
    p = 1
    IP, JP, gauss_im, I, J, pcont, IPd, JPd, IPs, JPs = HIIrecover_loop(ima=res, ima_err= ima_err, name=name, plot=plot, p=p, F_min=0)

    IPd_list = list(itertools.chain(IPd_list, IPd))
    JPd_list = list(itertools.chain(JPd_list, JPd))

    gfitim, cont, param = HIIplot2(IPs, JPs, gauss_im, ima=res, param=param)
    IP2 = list(itertools.chain(IP2, IP))
    JP2 = list(itertools.chain(JP2, JP))
    cont2 = list(itertools.chain(cont2, cont))
    I2 = list(itertools.chain(I2, I))
    J2 = list(itertools.chain(J2, J))
    pcont2 = list(itertools.chain(pcont2, pcont))
    gfitim_tot = Image(data=(gfitim_tot + gfitim), wcs=ima.wcs)
    grid = interpolate_continuum(ima=res,JP=JP, IP=IP, I=I, J=J, pcont=pcont, cont=cont, JP3=JP3, IP3=IP3, tcont=tcont, plot=False, F_min=0)
    gfitim2 = HIIplot_cont(gfitim=gfitim, grid=grid, ima=res)
    print(p)
    res = Image(data=(res.data - gfitim.data), wcs=ima.wcs)
    
    # chi2_global = chi_square(subima=ima, subima_err=ima_err, gfitim=gfitim2, parameter=1)
    # fig, ax = plt.subplots(1, 2, constrained_layout=True)
    # fig.suptitle('#{} {} HII regions - Chi2 {}'.format(p, len(IPs),np.round(chi2_global,2)), fontsize=16)      
    # gfitim2.plot(scale='log', vmin=0, vmax=np.amax(ima.data), colorbar='v', ax=ax[1],   zscale=False)
    # res.plot(scale='log', vmin=0, vmax=np.amax(ima.data), colorbar='v', ax=ax[0],   zscale=False)
    # ax[1].scatter(IPs, JPs, color='red', marker='.', linewidth=0.01)
    # plt.show()
    
    while (np.amax(res.data) > F_min) and (len(IP) != 0):
        p+=1
        # if p == 4:
        #     break
        res = Image(data=(res.data - gfitim.data), wcs=ima.wcs)
        # res = Image(data=(res.data - gfitim), wcs=ima.wcs)
        IP, JP, gauss_im, I, J, pcont, IPd, JPd, IPs, JPs = HIIrecover_loop(ima=res,  ima_err= ima_err, name=name, plot=plot, p=p, F_min=0)
        if len(IP) != 0:

            IPd_list = list(itertools.chain(IPd_list, IPd))
            JPd_list = list(itertools.chain(JPd_list, JPd))

            gfitim2, cont, param = HIIplot2(IPs, JPs, gauss_im, ima=res, param=param)
            
            grid = interpolate_continuum(ima=res,JP=JP, IP=IP, I=I, J=J, pcont=pcont, cont=cont, JP3=JP3, IP3=IP3, tcont=tcont, plot=False, F_min=0)
            gfitim2 = HIIplot_cont(gfitim=gfitim, grid=grid, ima=res)
            
            # chi2_global = chi_square(subima=ima, subima_err=ima_err, gfitim=gfitim2, parameter=1)
            # fig, ax = plt.subplots(1, 2, constrained_layout=True)
            # fig.suptitle('#{} {} HII regions - Chi2 {}'.format(p, len(IP),np.round(chi2_global,2)), fontsize=16)      
            # gfitim2.plot(scale='log', vmin=0, vmax=np.amax(ima.data), colorbar='v', ax=ax[1],   zscale=False)
            # res.plot(scale='log', vmin=0, vmax=np.amax(ima.data), colorbar='v', ax=ax[0],   zscale=False)
            # ax[1].scatter(IP, JP, color='red', marker='.', linewidth=0.01)
            # plt.show()
            
            gfitim, cont, param = HIIplot2(IPs, JPs, gauss_im, ima=res, param=param)
            cont2 = list(itertools.chain(cont2, cont))
            IP2 = list(itertools.chain(IP2, IP))
            JP2 = list(itertools.chain(JP2, JP))
            I2 = list(itertools.chain(I2, I))
            J2 = list(itertools.chain(J2, J))
            pcont2 = list(itertools.chain(pcont2, pcont))
            gfitim_tot = Image(data=(gfitim_tot.data + gfitim), wcs=ima.wcs)
            print(p)



    grid = interpolate_continuum(ima=ima,JP=JP2, IP=IP2, I=I2, J=J2, pcont=pcont2, cont=cont2,  JP3=JP3, IP3=IP3, tcont=tcont, plot=False, F_min=0)
    gfitim_tot2 = HIIplot_cont(gfitim=gfitim_tot, grid=grid, ima=res)
    if plot==True:
        fig = plt.figure()
        grid.plot(colorbar='v', scale='log', vmax=np.amax(ima.data))

    return gfitim_tot, gfitim_tot2, IP2, JP2, IPd_list, JPd_list, grid, param


def box_size(ima, subima):

    F_min = ima.background()

    I = 0
    I_list = []
    k = 0
    size = np.shape(subima)
    for i in range(1,np.amin(np.shape(subima))):
        subima.unmask()
        subima.mask_region(center=[(size[0]//2)-1,(size[1]//2)-1], radius=(i), unit_center=None, unit_radius=None, inside=False)
        #I = 2*np.pi*i*np.mean(subima.data)*np.exp(-(i**2)/(5**2))
        I = np.mean(subima.data)
        I_list.append(I)

    k = 1
    while ((I_list[k-1]-I_list[k]) > 0.5*F_min[1]) and (k<np.amin(np.shape(subima))):
        k+=1

    if k<np.amin(np.shape(subima)):
        return k
    elif k<10:
        return 10
    else:
        print("Could not find an optimal box size, default value was taken instead")
        return np.amin(np.shape(subima))


def box_size2(ima, subima):

    F_min = ima.background()

    I = 0
    I_list = []
    k = 0
    size = np.shape(subima)
    for i in range(1,np.amin(np.shape(subima))):
        subima.unmask()
        subima.mask_region(center=[(size[0]//2)-1,(size[1]//2)-1], radius=(i), unit_center=None, unit_radius=None, inside=False)
        #I = 2*np.pi*i*np.mean(subima.data)*np.exp(-(i**2)/(5**2))
        I = np.mean(subima.data)
        I_list.append(I)

    k = 1
    while ((I_list[k-1]-I_list[k]) > 0.5*F_min[1]) and (k<np.amin(np.shape(subima))):
        k+=1

    if k<np.amin(np.shape(subima)):
        return k
    elif k<3:
        return 3
    else:
        print("Could not find an optimal box size, default value was taken instead")
        return np.amin(np.shape(subima))

def error_ponderation(subima_err):
    (l,k) = np.shape(subima_err)
    xc, yc = l/2, k/2
    L = []
    for i in range(0,l):
        for j in range(0,k):
            L.append((1/l)*((i-xc)**2+(j-yc)**2)**0.5)
    L = np.array(L)
    L = np.reshape(L, (l,k))

    subima_err = Image(data=(subima_err.data + L), wcs=subima_err.wcs)
    return subima_err


def chi_square(subima, subima_err, gfitim, parameter):
    (n,m) = np.shape(subima)
    p = 0
    try:
        gfitim = gfitim.data
    except:
        gfitim = gfitim
    chi2 = 0
    subima=subima.data
    subima_err=subima_err.data
    for i in range(0,n):
        for j in range(0,m):
            if (isinstance(subima[i,j], float) == True) and (np.isnan(((subima[i,j]-gfitim[i,j])**2)/(subima_err[i,j]**2)) != True) and (subima_err[i,j] != 0 ):
                chi2+= ((subima[i,j]-gfitim[i,j])**2)/(subima_err[i,j]**2)
                p+=1
    normalization = p - parameter - 1
    return chi2/normalization


def gaussian(x, amp, xc, sigma):
    return amp*np.exp( -(x-xc)**2 / (2*sigma**2)) / np.sqrt(2*np.pi*sigma**2)

def gaussian_fit(x, noise, sigma = 0.001):
    # define some initial guess values for the fit routine
    # sigma = 0.001
    amp = 100*np.sqrt(2*np.pi*sigma**2)
    xc = 0
    guess_vals = [amp, xc, sigma]

    # perform the fit and calculate fit parameter errors from covariance matrix
    fit_params, cov_mat = curve_fit(gaussian, x, noise, p0=guess_vals)
    fit_errors = np.sqrt(np.diag(cov_mat))

    # manually calculate R-squared goodness of fit
    fit_residual = noise - gaussian(x, *fit_params)
    fit_Rsquared = 1 - np.var(fit_residual)/np.var(noise)
    return fit_params, fit_errors


def sigma(ima, plot=False):
    plt.figure()
    map_data = ima.data
    (n,m) = np.shape(ima)
    flux = []
    flux_inf0 = []
    for i in range(0,n):
        for j in range(0,m):
            if map_data[i,j] != 0:
                flux.append(map_data[i,j])
                if map_data[i,j] < 0:
                    flux_inf0.append(map_data[i,j])
    std = np.std(flux_inf0)

    n, bins, patches = plt.hist(flux, 2000, normed=1, facecolor='green', alpha=0.75)
    plt.close()
    bins2=[]
    for i in range(0, len(bins)-1):
        bins2.append(bins[i])


    fit_params, fit_errors = gaussian_fit(x=bins2, noise=n)

    (mu, sigma) = (fit_params[1], fit_params[2])

    if plot == True:
        fig, ax = plt.subplots(1, 1, constrained_layout=True)
        params = {'legend.fontsize': 15,
                'legend.handlelength': 2}
        plt.rcParams.update(params)
        plt.rc('text', usetex=True)
        n, bins, patches = plt.hist(flux, 2000, normed=1, facecolor='green', alpha=0.75)
        # add a 'best fit' line
        y = mlab.normpdf( bins, mu, sigma)
        l = plt.plot(bins, y, 'r--', linewidth=2, label=r'$\mathrm{Gaussian\ fit:}\ \mu=%.5f,\ \sigma=%.5f$' %(mu, sigma))

        # ax.axvline(-std, color='black', linestyle='dashed', label='$\sigma = %s$'%(np.round(std,5)))
        leg = plt.legend(loc='best', ncol=1, mode=None, shadow=False, fancybox=True)

        #plot
        plt.xlabel('Flux', fontsize=18)
        plt.ylabel('Number of pixels', fontsize=18)
        # plt.title(r'$\mathrm{Histogram\ of\ flux:}\ \mu=%.5f,\ \sigma=%.5f$' %(mu, sigma))
        plt.grid(True)
        ax.set_xlim([-0.015, 0.03])
        ax.set_ylim([0, 300])

        plt.show()
        plt.savefig(OUTPUT_TABLES_PATH + 'histogram_sigma_flux_{}.pdf'.format(name), bbox_inches='tight', transparent=True)

    return np.abs(sigma)

        


def reduce_size(ima, ima_err, name):
    ima_copy = ima.copy()
    (n,m) = np.shape(ima)
    i,j = 0,0
    A = 0
    while (i<m) and (A < flux_min(ima, name)):
        ima_copy = ima[0:n, m-i-2:m-i]
        A = np.mean(ima_copy.data)
        i+=2
    if m-i+50 < m:
        ima=ima[0:n, 0:m-i+50]
        ima_err=ima_err[0:n, 0:m-i+50]
    ima_copy = ima.copy()
    (n,m) = np.shape(ima)
    i = 0
    A = 0
    while (i<m) and (A < flux_min(ima, name)):
        ima_copy = ima[0:n, i:i+2]
        A = np.mean(ima_copy.data)
        i+=2
    if i-50 > 0:
        ima=ima[0:n, i-50:m]
        ima_err=ima_err[0:n, i-50:m]
    ima_copy = ima.copy()
    (n,m) = np.shape(ima)
    i = 0
    A = 0
    while (j<n) and (A < flux_min(ima, name)):
        ima_copy = ima[j:j+2, 0:m]
        A = np.mean(ima_copy.data)
        j+=2
    if j-50 > 0:
        ima=ima[j-50:n, 0:m]
        ima_err=ima_err[j-50:n, 0:m]
    ima_copy = ima.copy()
    (n,m) = np.shape(ima)
    i = 0
    A = 0
    while (j<n) and (A < flux_min(ima, name)):
        ima_copy = ima[n-j-2:n-j, 0:m]
        A = np.mean(ima_copy.data)
        j+=2
    if n-j+50 < n:
        ima=ima[0:n-j+50, 0:m]
        ima_err=ima_err[0:n-j+50, 0:m]
    return ima, ima_err


def cat(param, name):
    I1,I2,xc1,yc1,xc2,yc2,sigma1,sigma2,k,chi2,size,alpha,flux = param
    table_rows = []
    for i in range(0,len(param[0])):
        table_rows.append((alpha[i],I1[i],xc1[i],yc1[i],sigma1[i],I2[i],xc2[i],yc2[i],sigma2[i],k[i],chi2[i],size[i],flux[i]))

    t = Table(rows=table_rows, names=('alpha','I1','xc1','yc1','sigma1','I2','xc2','yc2','sigma2','cont','chi2','size','flux min',))
    t.sort('I1')
    t.write(OUTPUT_TABLES_PATH+'table_{}.dat'.format(name), format='ascii')
    return t


def chi_histogram(param, plot=False):
    I1,I2,xc1,yc1,xc2,yc2,sigma1,sigma2,k,chi2,size,alpha,flux = param
    I1a,I2a,xc1a,yc1a,xc2a,yc2a,sigma1a,sigma2a,ka,chi2a,sizea,alphaa,fluxa = [],[],[],[],[],[],[],[],[],[],[],[],[]
#    fig, ax = plt.subplots(1, 1, constrained_layout=True)
    #n, bins, patches = ax.hist(chi2, facecolor='green', bins=50, alpha=0.75)
    n, bins = np.histogram(chi2)
    bins2=[]
    I_list = []
    p = 0
    for i in range(0, len(bins)-1):
        bins2.append(bins[i])
    std = np.std(chi2)
#    ax.axvline(3*std, color='black', linestyle='dashed', label='{}'.format(np.round(3*std,2)))
#    plt.show()
#    plt.close()
    for i in range(0, len(chi2)):
        if chi2[i] > 3*std:
            I_list.append(i)
            
    for i in range(0, len(I1)):
        if i not in I_list:
            I1a.append(I1[i])
            I2a.append(I2[i])
            xc1a.append(xc1[i])
            yc1a.append(yc1[i])
            xc2a.append(xc2[i])
            yc2a.append(yc2[i])
            ka.append(k[i])
            chi2a.append(chi2[i])
            sizea.append(size[i])
            alphaa.append(alpha[i])
            fluxa.append(flux[i])
    
    param2 = I1a,I2a,xc1a,yc1a,xc2a,yc2a,sigma1a,sigma2a,ka,chi2a,sizea,alphaa,fluxa
    
    # fig, ax = plt.subplots(1, 1, constrained_layout=True)
    # n, bins, patches = ax.hist(chi2a, facecolor='green', bins=50, alpha=0.75)
    # plt.show()
    return I_list
            


def HIIplot(ima, param, plot=False):
    map_gfitim = np.zeros_like(ima)
    (n,m) = np.shape(ima)
    
    x = np.linspace(0, m, m)
    y = np.linspace(0, n, n)
    xy_mesh = np.meshgrid(x, y)
    
    alpha,I1,xc1,yc1,sigma1,I2,xc2,yc2,sigma2,cont,chi2,size = param

            
    if alpha[0] == 0:
        gfitim = gaussian_2dc(xy_mesh, I1[0],xc1[0],yc1[0],sigma1[0],0.0)
        
    elif alpha[0] == 1:
        gfitim = bimodal_gaussian_2d(xy_mesh, I1[0],xc1[0],yc1[0],sigma1[0], I2[0],xc2[0],yc2[0],sigma2[0],0.0)
       
    elif alpha[0] == 2:
        gfitim = gauss_image(shape=(n,m), gauss=None, center=(xc1[0], yc1[0]), unit_center=None, unit_fwhm=u.arcsec, flux=I1[0], peak=True, rot=0.0, fwhm=(sigma1[0],sigma1[0]), cont=0.0, wcs = ima.wcs, unit=ima.unit)
        gfitim = gfitim.data
        
    for i in range(1, len(alpha)):
        if alpha[i] == 0:
            gfitim = gfitim + gaussian_2dc(xy_mesh, I1[i],xc1[i],yc1[i],sigma1[i],0.0)
            
        elif alpha[i] == 1:
            gfitim = gfitim + bimodal_gaussian_2d(xy_mesh, I1[i],xc1[i],yc1[i],sigma1[i], I2[i],xc2[i],yc2[i],sigma2[i],0.0)
            
        elif alpha[i] == 2:
            gfitim2 = gauss_image(shape=(n,m), gauss=None, center=(xc1[i], yc1[i]), unit_center=None, unit_fwhm=u.arcsec, flux=I1[i], peak=True, rot=0.0, fwhm=(sigma1[i],sigma1[i]), cont=0.0, wcs = ima.wcs, unit=ima.unit)
            gfitim = gfitim + gfitim2.data
    
    if plot==True:
        plt.figure()
        gfitim=Image(data=(gfitim), wcs=ima.wcs)
        gfitim.plot(scale='log', vmin=0, vmax=np.amax(ima.data), colorbar='v',   zscale=False)
        plt.show()
    
    return gfitim


def read(cat):
    alpha=cat['alpha']
    I1 = cat['I1']
    xc1=cat['xc1']
    yc1=cat['yc1']
    sigma1=cat['sigma1']
    I2=cat['I2']
    xc2=cat['xc2']
    yc2=cat['yc2']
    sigma2=cat['sigma2']
    cont=cat['cont']
    chi2=cat['chi2']
    size=cat['size']
    return alpha,I1,xc1,yc1,sigma1,I2,xc2,yc2,sigma2,cont,chi2,size


def xav_explorer(ima, ima_err, name, plot=True):
    F_min    = flux_min(ima, name)
    IP2, JP2, gauss_im, I2, J2, pcont2, IPd, JPd, IPs, JPs = HIIrecover_loop(ima, ima_err, name=name, plot=False, F_min=0, p=0)
    gfitim, cont2, param = HIIplot2(IPs, JPs, gauss_im, ima, param=False)
    JP3, IP3, tcont = background_interpolation(ima, name)
    grid = interpolate_continuum(ima=ima,JP=JP2, IP=IP2, I=I2, J=J2, pcont=pcont2, cont=cont2, JP3=JP3, IP3=IP3, tcont=tcont, plot=False)
    gfitim2 = HIIplot_cont(gfitim, grid, ima)
    res = Image(data=(ima.data - gfitim.data), wcs=ima.wcs)
    p=0
    print(p)
    gfitim, gfitim2, IP2, JP2, IPd, JPd, grid, param = loop2(IP2, JP2, I2, J2, pcont2, cont2, gfitim, gfitim2, ima, ima_err, IPd, JPd, param, JP3, IP3, tcont, name, plot=False)
    res2 = Image(data=(ima.data - gfitim2.data), wcs=ima.wcs)

    catal = cat(param, name)
    I_list = chi_histogram(param, plot=True)
    b=0
    for k in range(0,len(I_list)):
        catal.remove_row(I_list[k]-b)
        b+=1
    param2 = read(cat=catal)
    gftim = HIIplot(ima, param2)
    gfitim2 = HIIplot_cont(gfitim, grid, ima)   
     
    cube = Cube(filename=MUSE_DATA_PATH+'flux_elines.{}.cube.fits.gz'.format(name))
    ima2 = cube[20, :, :]
    if name == 'ASASSN14jg':
        ima2=ima2[40:290, 20:260]
    chi2_global = chi_square(subima=ima2, subima_err=ima_err, gfitim=gfitim2, parameter=1)
    alpha=catal['alpha']
    if plot==True:
#        fig, ax = plt.subplots(2, 3, constrained_layout=True)
        fig, ax = plt.subplots(2, 3, figsize=(12,8))
        fig.suptitle('# {} HII regions - Chi2 {}'.format(len(alpha),np.round(chi2_global,2)), fontsize=16)
        ima.plot(scale='log', colorbar='v', ax=ax[0,0], vmin=0, vmax=np.amax(ima.data), zscale=False, title=r'flux = %s [10$^{-20}$ cgs]'%( np.round(np.sum(ima.data),2)))
        ax[0,1].scatter(IPd,JPd, color='red', marker='.', linewidth=0.01)
        res = Image(data=(ima.data - gfitim.data), wcs=ima.wcs)
        gfitim.plot(scale='log', vmin=0, vmax=np.amax(ima.data), colorbar='v', ax=ax[0,1],   zscale=False, title=r'flux = %s [10$^{-20}$ cgs]'%( np.round(np.sum(gfitim.data),2)))
        gfitim2.plot(scale='log', vmin=0, vmax=np.amax(ima.data), colorbar='v', ax=ax[0,2],   zscale=False, title=r'flux = %s [10$^{-20}$ cgs]'%( np.round(np.sum(gfitim2.data),2)))
        grid.plot(scale='log', vmin=0, vmax=np.amax(ima.data), colorbar='v', ax=ax[1,0],   zscale=False, title=r'flux = %s [10$^{-20}$ cgs]'%( np.round(np.sum(grid.data),2)))
        res2 = Image(data=(ima.data - gfitim2.data), wcs=ima.wcs)
        print('RESIDUALS: mean = {}, median = {}, std = {}'.format(np.round(np.mean(np.ravel(res2.data)),2), np.round(np.median(np.ravel(res2.data)),2), np.round(np.std(np.ravel(res2.data)),2)))#
#F_min
        #        res2.plot(vmin=np.amin(res2.data), vmax=np.amax(res2.data), colorbar='v', ax=ax[1,1],   zscale=False, title=r'flux = %s [10$^{-20}$ cgs]'%( np.round(np.sum(res2.data),2)))
        print("F_min"+str(F_min))
        res2.plot(vmin=-3*F_min, vmax=3*F_min, colorbar='v', ax=ax[1,1],   zscale=False, title=r'flux = %s [10$^{-20}$ cgs]'%( np.round(np.sum(res2.data),2)))
        res2.plot(scale='log', vmin=0, vmax=np.amax(ima.data), colorbar='v', ax=ax[1,2],   zscale=False, title='mean = {}, median = {}, std = {}'.format(np.round(np.mean(np.ravel(res2.data)),3), np.round(np.median(np.ravel(res2.data)),3), np.round(np.std(np.ravel(res2.data)),3)))
        fig.tight_layout()
        fig.savefig(OUTPUT_IMAGES_PATH + 'HII_recover_{}.pdf'.format(name), bbox_inches='tight', transparent=True)
        fig.savefig(OUTPUT_IMAGES_PATH + 'HII_recover_{}.png'.format(name), bbox_inches='tight', transparent=True)
        plt.close()

    return catal, grid, res2, gfitim, gfitim2, chi2_global
    

def flux_min(ima, name):
   std = sigma(ima)
   return 10*std


def scale_based_on_redshift(z):
    scale_now=1000*(1/0.2)*(1/1000)*(60)*1/(cosmo.kpc_proper_per_arcmin(z).value)
    return scale_now


if __name__=='__main__':

    nargs=len(sys.argv)
    nargs_need=3
    global name
    global redshift_input

    
    #    print("nargs="+str(nargs))
    if (nargs==nargs_need):
        name = sys.argv[1]
        redshift_input = np.float(sys.argv[2])
        #        fitscube,fitshdr=rfits_cube(filename)
    else:
        print("USE: HIIGaussian.py NAME_OF_CUBE REDSHIFT");
        print("There are some hard coded paths!");
        quit()

    start_time = time.time()
    name = 'ASASSN13bb'
    cube = Cube(filename=MUSE_DATA_PATH+'flux_elines.{}.cube.fits.gz'.format(name))
    ima = cube[20, :, :]
    ima_err = cube[140, :, :]
    
    catal, grid, res2, gfitim, gfitim2, chi2_global = xav_explorer(ima, ima_err, name, plot=True)
    

    print("My program took", time.time() - start_time, "seconds to run")
