# IRN_paddle

Invertible Image Rescaling ----Paddle 复现版本
https://paperswithcode.com/paper/invertible-image-rescaling
## 数据集

DIV2K
https://data.vision.ee.ethz.ch/cvl/DIV2K/
Set5
https://drive.google.com/drive/folders/1pRmhEmmY-tPF7uH8DuVthfHoApZWJ1QU

## 训练模型
Weigths/IRN.pdparams
## 训练步骤
### train sr
```bash
python train.py -opt config/train/train_Irn_x2.yml
```

## 测试步骤
```bash
python test.py -opt config/test/test_IRN.yml
```

