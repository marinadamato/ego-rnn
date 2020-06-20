import torch
import flow_resnet
import resnetMod
import torch.nn as nn
from objectAttentionModelConvLSTM import *

from MyConvLSTMCell import *


class attentionModel_flow(nn.Module):
    def __init__(self, flowModel='', frameModel='', num_classes=61, mem_size=512, attention=1):
        super(attentionModel_flow, self).__init__()
        self.num_classes = num_classes
        self.attention = attention
        self.resNetRGB = resnetMod.resnet34(True, True)
        if frameModel!='':
            self.resNetRGB.load_state_dict(OnlyResNet(torch.load(frameModel)))
        else:
            raise "No RGB dict provided"
        self.flowResNet = flow_resnet.flow_resnet34(True, channels=2, num_classes=61)
        self.mem_size = mem_size
        self.weight_softmax = self.resNet.fc.weight
        self.lstm_cell = MyConvLSTMCell(512, mem_size)
        self.avgpool = nn.AvgPool2d(7)
        self.dropout = nn.Dropout(0.7)
        self.fc = nn.Linear(mem_size, self.num_classes)
        self.classifier = nn.Sequential(self.dropout, self.fc)

    def forward(self, inputVariable_flow, inputVariable_rgb):
        state = (torch.zeros((inputVariable_flow.size(1), self.mem_size, 7, 7).cuda()),
                 torch.zeros((inputVariable_flow.size(1), self.mem_size, 7, 7).cuda()))
        #self.resNetRGB.train(False)
        for t in range(inputVariable_flow.size(0)):
            logit, feature_conv = self.flowResNet(inputVariable_flow[t])
            _, _, feature_convNBN = self.resNetRGB(inputVariable_rgb[t])
            if self.attention == 1: 
                bz, nc, h, w = feature_conv.size()
                feature_conv1 = feature_conv.view(bz, nc, h*w)
                probs, idxs = logit.sort(1, True)
                class_idx = idxs[:, 0]
                cam = torch.bmm(self.weight_softmax[class_idx].unsqueeze(1), feature_conv1)
                attentionMAP = torch.softmax(cam.squeeze(1), dim=1)
                attentionMAP = attentionMAP.view(attentionMAP.size(0), 1, 7, 7)
                attentionFeat = feature_convNBN * attentionMAP.expand_as(feature_conv)
                state = self.lstm_cell(attentionFeat, state)
            elif self.attention == 0:
                state = self.lstm_cell(feature_conv, state)
        feats1 = self.avgpool(state[1]).view(state[1].size(0), -1)
        feats = self.classifier(feats1)
        return feats, feats1

class twoStreamAttentionModel(nn.Module):
    def __init__(self, flowModel='', frameModel='', stackSize=5, memSize=512, num_classes=61):
        super(twoStreamAttentionModel, self).__init__()
        self.flowModel = attentionModel_flow(frameModel='', num_classes=num_classes, mem_size=mem_size)
        if flowModel != '':
            self.flowModel.load_state_dict(torch.load(flowModel))
        self.frameModel = attentionModel(num_classes, memSize)
        if frameModel != '':
            self.frameModel.load_state_dict(torch.load(frameModel))
        self.fc2 = nn.Linear(512 * 2, num_classes, bias=True)
        self.dropout = nn.Dropout(0.5)
        self.classifier = nn.Sequential(self.dropout, self.fc2)

    def forward(self, inputVariableFlow, inputVariableFrame):
        _, flowFeats = self.flowModel(inputVariableFlow)
        _, rgbFeats = self.frameModel(inputVariableFrame)
        twoStreamFeats = torch.cat((flowFeats, rgbFeats), 1)
        return self.classifier(twoStreamFeats)


def OnlyResNet(diction):
    res_key=[]
    for key in diction.keys():
        if key[:7]=='resNet.': 
            res_key.append(key)

    return {k: diction[k] for k in res_key}
