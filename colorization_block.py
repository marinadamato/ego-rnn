import torch
from resnetMod import resnet34
from flow_resnet import flow_resnet34
import torch.nn as nn
from torch.nn import functional as F
from torch.autograd import Variable
from MyConvLSTMCell import *
from objectAttentionModelConvLSTM import attentionModel
from PIL import Image
import numpy as np
from torchvision.utils import save_image
from spatial_transforms import Normalize
import os

class residual_block(nn.Module):
    def __init__(self):
        super(residual_block,self).__init__()
        self.conv1 = nn.Conv2d(64,64, kernel_size=3, stride=1,padding= 1)
        self.bn1 = nn.BatchNorm2d(64)
        self.relu1 = nn.LeakyReLU(negative_slope=0.02, inplace=True)
        self.conv2 = nn.Conv2d(64,64, kernel_size=3, stride=1,padding= 1)
        self.bn2 = nn.BatchNorm2d(64)
        self.relu2 = nn.LeakyReLU(negative_slope=0.02, inplace=True)
        

    def forward(self,x):
        x_p=x
        x= self.conv1(x)     
        x= self.bn1(x)
        x=self.relu1(x)
        x=self.conv2(x)
        x=self.bn2(x)
        x= x_p + x 
        x=self.relu2(x)
        return x


class colorization(nn.Module):
    def __init__(self,num_classes=61):
        
        super(colorization, self).__init__()
        self.conv1 = nn.Conv2d(2, 64, kernel_size=7, stride=2, padding=3,
                               bias=False)
        self.bn1 = nn.BatchNorm2d(64)
        self.relu = nn.LeakyReLU(negative_slope=0.01, inplace=True)
        self.maxpool = nn.MaxPool2d(kernel_size=3, stride=2)
        self.residual_block=[]
        for i in range(4):
            self.residual_block.append(residual_block())
        self.residual_block = nn.Sequential(*self.residual_block)
        self.conv2 = nn.Conv2d(64, 3, kernel_size= 1, stride=1, padding=0, bias=False)
        #self.deconv= nn.ConvTranspose2d(3, 3, 8, stride=4, padding=0, groups=1, bias=False)
        self.upS = nn.Sequential(nn.Upsample(224,mode='bilinear'),
                    nn.Conv2d(3,3, kernel_size= 1, stride=1, padding=0, bias=False))
        self.RGBnet = attentionModel(num_classes=num_classes, mem_size=512)
        self.k=0

    def forward(self,inputVariable,f_print=0):
        flow_list =[]
        for t in range(inputVariable.size(0)):
            x=self.conv1(inputVariable[t])
            
            x=self.bn1(x) 
            x=self.relu(x) 
            x=self.maxpool(x)
            
            
            x=self.residual_block(x)

            x=self.conv2(x) 
            x=self.upS(x)
            flow_list.append(x)
        flow_list = torch.stack(flow_list, 0)
        if f_print==1:
            self.k+=1
            path='/content/Images/'+str(self.k)
            os.mkdir(path)
            for j in range(flow_list.size(1)):
                T=flow_list[7][j].data
                save_image(inputVariable[7][j][0],path +'/e{}_x{}.jpg'.format(self.k,j))
                save_image(inputVariable[7][j][1],path +'/e{}_y{}.jpg'.format(self.k,j))
                save_image(T,path+ "/e{}_color{}.jpg".format(self.k,j))
            print('new image')
        x=self.RGBnet(flow_list)
        return x
        
