import math
import paddle
import paddle.nn as nn
import paddle.nn.functional as F
import numpy as np


class InvBlockExp(nn.Layer):
    def __init__(self, subnet_constructor, channel_num, channel_split_num, clamp=1.):
        super(InvBlockExp, self).__init__()

        self.split_len1 = channel_split_num
        self.split_len2 = channel_num - channel_split_num

        self.clamp = clamp

        self.F = subnet_constructor(self.split_len2, self.split_len1)
        self.G = subnet_constructor(self.split_len1, self.split_len2)
        self.H = subnet_constructor(self.split_len1, self.split_len2)

    def forward(self, x, rev=False):
        x1 =paddle.slice(x,[1],[0],[self.split_len1])
        x2 =paddle.slice(x,[1],[self.split_len1],[12])
        
        # x1, x2 = (x.narrow(1, 0, self.split_len1), x.narrow(1, self.split_len1, self.split_len2))

        if not rev:
            y1 = x1 + self.F(x2)
            self.s = self.clamp * (paddle.nn.functional.sigmoid(self.H(y1)) * 2 - 1)
            # y2 = x2.mul(paddle.exp(self.s)) + self.G(y1)
            y2=paddle.multiply(x2,paddle.exp(x2,self.s)) + self.G(y1)
        else:
            self.s = self.clamp * (paddle.nn.functional.sigmoid(self.H(x1)) * 2 - 1)
            # y2 = (x2 - self.G(x1)).div(paddle.exp(self.s))
            y2=paddle.divide((x2 - self.G(x1)),paddle.exp(self.s))
            y1 = x1 - self.F(y2)

        return paddle.concat((y1, y2), 1)

    def jacobian(self, x, rev=False):
        if not rev:
            jac = paddle.sum(self.s)
        else:
            jac = -paddle.sum(self.s)

        return jac / x.shape[0]


class HaarDownsampling(nn.Layer):
    def __init__(self, channel_in):
        super(HaarDownsampling, self).__init__()
        self.channel_in = channel_in

        self.haar_weights = paddle.ones((4, 1, 2, 2))

        self.haar_weights[1, 0, 0, 1] = -1
        self.haar_weights[1, 0, 1, 1] = -1

        self.haar_weights[2, 0, 1, 0] = -1
        self.haar_weights[2, 0, 1, 1] = -1

        self.haar_weights[3, 0, 1, 0] = -1
        self.haar_weights[3, 0, 0, 1] = -1

        self.haar_weights = paddle.concat([self.haar_weights] * self.channel_in, 0)
        # self.haar_weights = nn.Parameter(self.haar_weights)
        self.haar_weights = paddle.create_parameter(shape=self.haar_weights.shape,
                        dtype=self.haar_weights.dtype,
                        default_initializer=paddle.nn.initializer.Assign(self.haar_weights))
        self.haar_weights.requires_grad = False

    def forward(self, x, rev=False):
        if not rev:
            self.elements = x.shape[1] * x.shape[2] * x.shape[3]
            self.last_jac = self.elements / 4 * np.log(1/16.)

            out = F.conv2d(x, self.haar_weights, bias=None, stride=2, groups=self.channel_in) / 4.0
            out = out.reshape([x.shape[0], self.channel_in, 4, x.shape[2] // 2, x.shape[3] // 2])
            # out = paddle.transpose(out, 1, 2)
            out = paddle.transpose(out, perm=[0, 2, 1,3,4])
            
            out = out.reshape([x.shape[0], self.channel_in * 4, x.shape[2] // 2, x.shape[3] // 2])
            return out
        else:
            self.elements = x.shape[1] * x.shape[2] * x.shape[3]
            self.last_jac = self.elements / 4 * np.log(16.)

            out = x.reshape([x.shape[0], 4, self.channel_in, x.shape[2], x.shape[3]])
            # out = paddle.transpose(out, 1, 2)
            out = paddle.transpose(out, perm=[0, 2, 1,3,4])
            out = out.reshape([x.shape[0], self.channel_in * 4, x.shape[2], x.shape[3]])
            return paddle.nn.functional.conv2d_transpose(out, self.haar_weights, bias=None, stride=2, groups = self.channel_in)

    def jacobian(self, x, rev=False):
        return self.last_jac


class ConvDownsampling(nn.Layer):
    def __init__(self, scale):
        super(ConvDownsampling, self).__init__()
        self.scale = scale
        self.scale2 = self.scale ** 2

        self.conv_weights = paddle.eye(self.scale2)

        if self.scale == 2: # haar init
            self.conv_weights[0] = paddle.Tensor([1./4, 1./4, 1./4, 1./4])
            self.conv_weights[1] = paddle.Tensor([1./4, -1./4, 1./4, -1./4])
            self.conv_weights[2] = paddle.Tensor([1./4, 1./4, -1./4, -1./4])
            self.conv_weights[3] = paddle.Tensor([1./4, -1./4, -1./4, 1./4])
        else:
            self.conv_weights[0] = paddle.Tensor([1./(self.scale2)] * (self.scale2))

        self.conv_weights = nn.Parameter(self.conv_weights)

    def forward(self, x, rev=False):
        if not rev:
            # downsample
            # may need improvement
            h = x.shape[2]
            w = x.shape[3]
            wpad = 0
            hpad = 0
            if w % self.scale != 0:
                wpad = self.scale - w % self.scale
            if h % self.scale != 0:
                hpad = self.scale - h % self.scale
            if wpad != 0 or hpad != 0:
                padding = (wpad // 2, wpad - wpad // 2, hpad // 2, hpad - hpad // 2)
                pad = nn.ReplicationPad2d(padding)
                x = pad(x)

            [B, C, H, W] = list(x.size())
            x = x.reshape(B, C, H // self.scale, self.scale, W // self.scale, self.scale)
            x = x.permute(0, 1, 3, 5, 2, 4)
            x = x.reshape(B, C * self.scale2, H // self.scale, W // self.scale)

            # conv
            conv_weights = self.conv_weights.reshape(self.scale2, self.scale2, 1, 1)
            conv_weights = conv_weights.repeat(C, 1, 1, 1)

            out = F.conv2d(x, conv_weights, bias=None, stride=1, groups=C)

            out = out.reshape(B, C, self.scale2, H // self.scale, W // self.scale)
            out = paddle.transpose(out, 1, 2)
            out = out.reshape(B, C * self.scale2, H // self.scale, W // self.scale)

            return out
        else:
            inv_weights = paddle.inverse(self.conv_weights)
            inv_weights = inv_weights.reshape(self.scale2, self.scale2, 1, 1)

            [B, C_, H_, W_] = list(x.size())
            C = C_ // self.scale2
            H = H_ * self.scale
            W = W_ * self.scale

            inv_weights = inv_weights.repeat(C, 1, 1, 1)

            x = x.reshape(B, self.scale2, C, H_, W_)
            x = paddle.transpose(x, 1, 2)
            x = x.reshape(B, C_, H_, W_)

            out = F.conv2d(x, inv_weights, bias=None, stride=1, groups=C)

            out = out.reshape(B, C, self.scale, self.scale, H_, W_)
            out = out.permute(0, 1, 4, 2, 5, 3)
            out = out.reshape(B, C, H, W)

            return out


class InvRescaleNet(nn.Layer):
    def __init__(self, channel_in=3, channel_out=3, subnet_constructor=None, block_num=[], down_num=2, down_first=False, use_ConvDownsampling=False, down_scale=4):
        super(InvRescaleNet, self).__init__()

        operations = []

        if use_ConvDownsampling:
            down_num = 1
            down_first = True

        current_channel = channel_in
        if down_first:
            for i in range(down_num):
                if use_ConvDownsampling:
                    b = ConvDownsampling(down_scale)
                    current_channel *= down_scale**2
                else:
                    b = HaarDownsampling(current_channel)
                    current_channel *= 4
                operations.append(b)
            for j in range(block_num[0]):
                b = InvBlockExp(subnet_constructor, current_channel, channel_out)
                operations.append(b)
        else:
            for i in range(down_num):
                b = HaarDownsampling(current_channel)
                operations.append(b)
                current_channel *= 4
                for j in range(block_num[i]):
                    b = InvBlockExp(subnet_constructor, current_channel, channel_out)
                    operations.append(b)

        self.operations = nn.LayerList(operations)

    def forward(self, x, rev=False, cal_jacobian=False):
        out = x
        jacobian = 0

        if not rev:
            for op in self.operations:
                out = op.forward(out, rev)
                if cal_jacobian:
                    jacobian += op.jacobian(out, rev)
        else:
            for op in reversed(self.operations):
                out = op.forward(out, rev)
                if cal_jacobian:
                    jacobian += op.jacobian(out, rev)

        if cal_jacobian:
            return out, jacobian
        else:
            return out


class Conv1x1Grey(nn.Layer):
    def __init__(self, rgb_type, learnable=True):
        super(Conv1x1Grey, self).__init__()

        self.channel_in = 3
        self.conv_weights = paddle.eye(self.channel_in)
        if rgb_type == 'RGB':
            self.conv_weights[0] = paddle.Tensor([0.299, 0.587, 0.114])
            self.conv_weights[1] = paddle.Tensor([-0.147, -0.289, 0.436])
            self.conv_weights[2] = paddle.Tensor([0.615, -0.515, -0.100])
        elif rgb_type == 'BGR':
            self.conv_weights[0] = paddle.Tensor([0.114, 0.587, 0.299])
            self.conv_weights[1] = paddle.Tensor([0.436, -0.289, -0.147])
            self.conv_weights[2] = paddle.Tensor([-0.100, -0.515, 0.615])
        else:
            print("Error! Undefined RGB type!")
            exit(1)

        self.conv_weights = nn.Parameter(self.conv_weights)

        if not learnable:
            self.conv_weights.requires_grad = False

    def forward(self, x, rev=False):
        if not rev:
            conv_weights = self.conv_weights.reshape(self.channel_in, self.channel_in, 1, 1)
            out = F.conv2d(x, conv_weights, bias=None, stride=1)
            return out
        else:
            inv_weights = paddle.inverse(self.conv_weights)
            inv_weights = inv_weights.reshape(self.channel_in, self.channel_in, 1, 1)
            out = F.conv2d(x, inv_weights, bias=None, stride=1)
            return out


class InvGreyNet(nn.Layer):
    def __init__(self, rgb_type, subnet_constructor=None, block_num=[], Conv1x1Grey_learnable=True):
        super(InvGreyNet, self).__init__()

        channel_in = 3
        channel_out = 1

        operations = []

        b = Conv1x1Grey(rgb_type, Conv1x1Grey_learnable)
        operations.append(b)

        for j in range(block_num[0]):
            b = InvBlockExp(subnet_constructor, channel_in, channel_out)
            operations.append(b)

        self.operations = nn.LayerList(operations)

    def forward(self, x, rev=False, cal_jacobian=False):
        out = x
        jacobian = 0

        if not rev:
            for op in self.operations:
                out = op.forward(out, rev)
                if cal_jacobian:
                    jacobian += op.jacobian(out, rev)
        else:
            for op in reversed(self.operations):
                out = op.forward(out, rev)
                if cal_jacobian:
                    jacobian += op.jacobian(out, rev)

        if cal_jacobian:
            return out, jacobian
        else:
            return out