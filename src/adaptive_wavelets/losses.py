import os, sys
import numpy as np
import torch
import torch.nn as nn
from torch.nn import functional as F


def get_loss_f(**kwargs_parse):
    """Return the loss function given the argparse arguments."""
    return Loss(lamSum=kwargs_parse["lamSum"], 
                lamL2norm=kwargs_parse["lamL2norm"],
                lamCMF = kwargs_parse["lamCMF"],
                lamL1wave = kwargs_parse["lamL1wave"],
                lamL1attr=kwargs_parse["lamL1attr"])


class Loss():
    """Class of calculating loss functions
    """
    def __init__(self, lamSum=0., lamL2norm=0., lamCMF=0., lamL1wave=0., lamL1attr=0.):
        """
        Parameters
        ----------
        lamSum : float
            Hyperparameter for penalizing sum of lowpass filter
            
        lamL2norm : float
            Hyperparameter to enforce unit norm of lowpass filter
            
        lamCMF : float 
            Hyperparameter to enforce conjugate mirror filter   
            
        lamL1wave : float
            Hyperparameter for penalizing L1 norm of wavelet coeffs
        
        lamL1attr : float
            Hyperparameter for penalizing L1 norm of attributions
        """    
        self.lamSum = lamSum
        self.lamL2norm = lamL2norm
        self.lamCMF = lamCMF
        self.lamL1wave = lamL1wave
        self.lamL1attr = lamL1attr

    def __call__(self, w_transform, data, recon_data, data_t, attributions=None):
        """
        Parameters
        ----------
        w_transform : wavelet object
        
        data : torch.Tensor
            Input data (e.g. batch of images). Shape : (batch_size, n_chan,
            height, width).

        recon_data : torch.Tensor
            Reconstructed data. Shape : (batch_size, n_chan, height, width).
            
        data_t: list of torch.Tensor
            Input data after wavelet transform.
            
        attributions: torch.Tensor
            Input attribution scores.          

        Return
        ------
        loss : torch.Tensor
        """        
        self.rec_loss = _reconstruction_loss(data, recon_data)
        
        # sum of lowpass filter
        self.sum_loss = 0
        if self.lamSum > 0:
            self.sum_loss += _sum_loss(w_transform)
            
        # l2norm of lowpass filter
        self.L2norm_loss = 0
        if self.lamL2norm > 0:
            self.L2norm_loss += _L2norm_loss(w_transform)
            
        # conjugate mirror filter condition
        self.CMF_loss = 0
        if self.lamCMF > 0:
            self.CMF_loss += _CMF_loss(w_transform)
            
        # L1 penalty on wavelet coeffs
        self.L1wave_loss = 0
        if self.lamL1wave > 0:
            self.L1wave_loss += _L1_wave_loss(data_t)
        
        # L1 penalty on attributions
        self.L1attr_loss = 0
        if self.lamL1attr > 0:
            self.L1attr_loss += _L1_attribution_loss(attributions)

        # total loss
        loss = self.rec_loss + self.lamSum*self.sum_loss + self.lamL2norm*self.L2norm_loss + \
                + self.lamCMF*self.CMF_loss + self.lamL1wave*self.L1wave_loss + self.lamL1attr*self.L1attr_loss    
        
        return loss
            


def _reconstruction_loss(data, recon_data):
    """
    Calculates the per image reconstruction loss for a batch of data. I.e. negative
    log likelihood.
    
    Parameters
    ----------
    data : torch.Tensor
        Input data (e.g. batch of images). Shape : (batch_size, n_chan,
        height, width).
    recon_data : torch.Tensor
        Reconstructed data. Shape : (batch_size, n_chan, height, width).
        
    Returns
    -------
    loss : torch.Tensor
        Per image cross entropy (i.e. normalized per batch but not pixel and
        channel)
    """
    batch_size = recon_data.size(0)
    loss = F.mse_loss(recon_data, data, reduction="sum")
    loss = loss / batch_size

    return loss


def _sum_loss(w_transform):
    """
    Calculate sum of lowpass filter
    """    
    h0 = w_transform.h0
    loss = .5*(h0.sum() - np.sqrt(2))**2
    
    return loss


def _L2norm_loss(w_transform):
    """
    Calculate L2 norm of lowpass filter
    """    
    h0 = w_transform.h0
    loss = .5*((h0**2).sum() - 1)**2
    
    return loss


def _CMF_loss(w_transform):
    """
    Calculate conjugate mirror filter condition
    """    
    h0 = w_transform.h0
    n = h0.size(2)
    assert n%2==0, "length of lowpass filter should be even"
    h_f = torch.fft(torch.stack((h0, torch.zeros_like(h0)),dim=3), 1)
    mod = (h_f**2).sum(axis=3)
    cmf_identity = mod[0,0,:n//2] + mod[0,0,n//2:]  
    loss = torch.sum((cmf_identity - 2)**2)/n
    
    return loss


def _L1_wave_loss(coeffs):
    """
    Calculate L1 norm of wavelet coefficients
    """
    batch_size = coeffs[0].size(0)
    loss = tuple_L1Loss(coeffs)
    loss = loss / batch_size

    return loss
    

def _L1_attribution_loss(attributions):
    """
    Calculate L1 norm of the attributions
    """
    batch_size = attributions[0].size(0)
    loss = tuple_L1Loss(attributions)
    loss = loss / batch_size

    return loss


def tuple_L1Loss(x):
    output = 0
    num = len(x)
    for i in range(num):
        output += torch.sum(abs(x[i]))
    return output/num


def tuple_L2Loss(x):
    output = 0
    num = len(x)
    for i in range(num):
        output += torch.sum(x[i]**2)
    return output/num  