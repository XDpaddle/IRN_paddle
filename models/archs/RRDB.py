import functools
import paddle
import paddle.nn as nn
# import torch.nn.functional as F
import models.module_util as mutil

class ResidualDenseBlock_5C(nn.Layer):
    def __init__(self, nf=64, gc=32, bias=True):
        super(ResidualDenseBlock_5C, self).__init__()
        self.conv1 = nn.Conv2D(nf, gc, 3, 1, 1, bias=bias)
        self.conv2 = nn.Conv2D(nf + gc, gc, 3, 1, 1, bias=bias)
        self.conv3 = nn.Conv2D(nf + 2 * gc, gc, 3, 1, 1, bias=bias)
        self.conv4 = nn.Conv2D(nf + 3 * gc, gc, 3, 1, 1, bias=bias)
        self.conv5 = nn.Conv2D(nf + 4 * gc, nf, 3, 1, 1, bias=bias)
        self.lrelu = nn.LeakyReLU(negative_slope=0.2, inplace=True)

        #mutil.initialize_weights([self.conv1, self.conv2, self.conv3, self.conv4, self.conv5], 0.1)
        mutil.initialize_weights([self.conv1, self.conv2, self.conv3, self.conv4], 0.1)
        mutil.initialize_weights(self.conv5, 0)

    def forward(self, x):
        x1 = self.lrelu(self.conv1(x))
        x2 = self.lrelu(self.conv2(paddle.concat((x, x1), 1)))
        x3 = self.lrelu(self.conv3(paddle.concat((x, x1, x2), 1)))
        x4 = self.lrelu(self.conv4(paddle.concat((x, x1, x2, x3), 1)))
        x5 = self.conv5(paddle.concat((x, x1, x2, x3, x4), 1))

        return x5 * 0.2 + x


class RRDB(nn.Layer):
    def __init__(self, nf, gc=32):
        super(RRDB, self).__init__()
        self.RDB1 = ResidualDenseBlock_5C(nf, gc)
        self.RDB2 = ResidualDenseBlock_5C(nf, gc)
        self.RDB3 = ResidualDenseBlock_5C(nf, gc)

    def forward(self, x):
        out = self.RDB1(x)
        out = self.RDB2(out)
        out = self.RDB3(out)

        return out * 0.2 + x

class RRDBNet(nn.Layer):
    def __init__(self, in_nc, out_nc, nf, nb, gc=32):
        super(RRDBNet, self).__init__()
        RRDB_block_f = functools.partial(RRDB, nf=nf, gc=gc)

        self.conv_first = nn.Conv2D(in_nc, nf, 3, 1, 1, bias=True)
        self.RRDB_trunk = mutil.make_layer(RRDB_block_f, nb)
        self.trunk_conv = nn.Conv2D(nf, nf, 3, 1, 1, bias=True)
        self.conv_last = nn.Conv2D(nf, out_nc, 3, 1, 1, bias=True)

        self.lrelu = nn.LeakyReLU(negative_slope=0.2, inplace=True)

    def forward(self, x):
        fea = self.conv_first(x)
        trunk = self.trunk_conv(self.RRDB_trunk(fea))
        fea = fea + trunk

        out = self.conv_last(fea)

        return out