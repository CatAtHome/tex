import torch
import torch.nn as nn
from typing import Type


def call(func, value): return func(value) if callable(func) else value


class Block(nn.Module):

    expansion = 1

    def __init__(self, in_planes, planes, stride=(1, 1), sub=None):
        super(Block, self).__init__()
        assert stride[0] > 0 and stride[1] > 0
        self.sub_method = sub
        self.downsample = None
        if (stride[0] > 1 or stride[1] > 1) or (in_planes != planes * self.expansion):
            self.downsample = nn.Sequential(
                nn.Conv2d(
                    in_planes, planes * self.expansion, (1, 1), stride=stride, bias=False),
                nn.BatchNorm2d(planes * self.expansion),
            )

    def forward(self, x):  # pre-activation
        return call(self.sub_method, self.net(x)) + call(self.downsample, x)


class BasicBlock(Block):

    def __init__(self, in_planes, planes, stride=(1, 1), sub=None):
        super(BasicBlock, self).__init__(in_planes, planes, stride, sub)
        self.net = nn.Sequential(
            nn.BatchNorm2d(in_planes),
            nn.ReLU(inplace=True),
            nn.Conv2d(in_planes, planes, (3, 3), padding=(1, 1), stride=stride),
            nn.BatchNorm2d(planes),
            nn.ReLU(inplace=True),
            nn.Conv2d(planes, planes * self.expansion, (3, 3), padding=(1, 1)),
        )


class Bottleneck(Block):

    expansion = 4

    def __init__(self, in_planes, planes, stride=(1, 1), sub=None):
        super(Bottleneck, self).__init__(in_planes, planes, stride, sub)
        self.net = nn.Sequential(
            nn.BatchNorm2d(in_planes),
            nn.ReLU(inplace=True),
            nn.Conv2d(in_planes, planes, (1, 1)),
            nn.BatchNorm2d(planes),
            nn.ReLU(inplace=True),
            nn.Conv2d(planes, planes, (3, 3), padding=(1, 1), stride=stride),
            nn.BatchNorm2d(planes),
            nn.ReLU(inplace=True),
            nn.Conv2d(planes, planes * self.expansion, (1, 1)),
        )


class BottleneckX(Block):

    expansion = 2

    def __init__(self, in_planes, planes, stride=(1, 1), groups=32, sub=None):
        super(BottleneckX, self).__init__(in_planes, planes, stride, sub)
        self.net = nn.Sequential(
            nn.BatchNorm2d(in_planes),
            nn.ReLU(inplace=True),
            nn.Conv2d(in_planes, planes, (1, 1)),
            nn.BatchNorm2d(planes),
            nn.ReLU(inplace=True),
            nn.Conv2d(planes, planes, (3, 3), padding=(1, 1), stride=stride, groups=groups),
            nn.BatchNorm2d(planes),
            nn.ReLU(inplace=True),
            nn.Conv2d(planes, planes * self.expansion, (1, 1)),
        )


class CotAttention(nn.Module):

    def __init__(self, d_model, d_hidden, kernel_size, stride=(1, 1), padding=(0, 0)):
        super(CotAttention, self).__init__()
        assert kernel_size[0] % 2 and (kernel_size[0] - 1) // 2 == padding[0]
        assert kernel_size[1] % 2 and (kernel_size[1] - 1) // 2 == padding[1]
        self.alpha = kernel_size[0] * kernel_size[1]
        self.key_mapping = nn.Sequential(  # TODO: why groups
            nn.Conv2d(d_model, d_model, kernel_size, padding=padding, bias=False),
            nn.BatchNorm2d(d_model),
            nn.ReLU(inplace=True)
        )
        self.val_mapping = nn.Sequential(
            nn.Conv2d(d_model, d_model, (1, 1), bias=False),
            nn.BatchNorm2d(d_model)
        )
        self.atn_mapping = nn.Sequential(
            nn.Conv2d(2 * d_model, d_hidden, (1, 1), bias=False),
            nn.BatchNorm2d(d_hidden),
            nn.ReLU(inplace=True),
            nn.Conv2d(d_hidden, d_model * self.alpha, (1, 1))
        )
        self.downsample = None
        if stride[0] > 1 or stride[1] > 1:
            self.downsample = nn.AvgPool2d(kernel_size, stride=stride, padding=padding)

    def forward(self, x):
        x = call(self.downsample, x)
        k_1 = self.key_mapping(x)  # bs,c,h,w
        val = self.val_mapping(x).view(x.size(0), x.size(1), -1)  # bs,c,h*w
        atn = self.atn_mapping(torch.cat([k_1, x], dim=1))  # bs,c*alpha,h,w
        atn = atn.view(x.size(0), x.size(1), self.alpha, x.size(2), x.size(3))
        atn = atn.mean(2, keepdim=False).view(x.size(0), x.size(1), -1)  # bs,c,h*w
        k_2 = torch.softmax(atn, dim=-1) * val  # bs,c,h*w
        return k_1 + k_2.view(*x.size())  # bs,c,h,w


class ContextualBlock(Block):

    expansion = 4

    def __init__(self, in_planes, planes, stride=(1, 1), sub=None):
        super(ContextualBlock, self).__init__(in_planes, planes, stride, sub)
        self.net = nn.Sequential(
            nn.BatchNorm2d(in_planes),
            nn.ReLU(inplace=True),
            nn.Conv2d(in_planes, planes, (1, 1)),
            nn.BatchNorm2d(planes),
            nn.ReLU(inplace=True),
            CotAttention(planes, planes, (3, 3), stride=stride, padding=(1, 1)),
            nn.BatchNorm2d(planes),
            nn.ReLU(inplace=True),
            nn.Conv2d(planes, planes * self.expansion, (1, 1)),
        )


def make_layer(layers: int, block: Type[Block],
               in_planes, planes, stride=(1, 1), sub=None):
    return nn.Sequential(
        block(in_planes, planes, stride=stride, sub=sub),
        *[
            block(
                planes * block.expansion, planes, sub=sub
            ) for _ in range(1, layers)
        ]
    )


if __name__ == '__main__':
    net = ContextualBlock(64, 32, (2, 2))
    i = torch.randn((10, 64, 56, 56))
    print(net(i).size())
