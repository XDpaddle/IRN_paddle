# IRN_paddle

Invertible Image Rescaling ----Paddle 复现版本

## 数据集

分类之后训练集用于训练SR模块
https://aistudio.baidu.com/aistudio/datasetdetail/106261

## 训练模型
Weigths/IRN.pdparams
## 训练步骤
### train sr
```bash
python train.py -opt config/train/train_Irn_x2.yml
```

```
多卡仅需
```bash
python -m paddle.distributed.launch train.py --launcher fleet -opt config_file_path
python -m paddle.distributed.launch train_ClassSR.py --launcher fleet -opt config_file_path
```
## 测试步骤
```bash
python test.py -opt config/test/test_IRN.yml
```

