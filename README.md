# Applying BP2MN to Semantic Segmentation

Our segmentation code is developed on top of [MMSegmentation v0.20.2](https://github.com/open-mmlab/mmsegmentation/tree/v0.20.2).



## Usage

Install [MMSegmentation v0.20.2](https://github.com/open-mmlab/mmsegmentation/tree/v0.20.2).

```
# recommended environment: torch1.9 + cuda11.1
pip install torch==1.9.0+cu111 torchvision==0.10.0+cu111 torchaudio==0.9.0 -f https://download.pytorch.org/whl/torch_stable.html
pip install mmcv-full==1.4.2 -f https://download.openmmlab.com/mmcv/dist/cu111/torch1.9.0/index.html
pip install timm==0.4.12
pip install mmdet==2.22.0 # for Mask2Former
pip install mmsegmentation==0.20.2
ln -s ../detection/ops ./
cd ops & sh make.sh # compile deformable attention
```

## Main Results and Models

**ADE20K val**





| Method  | Backbone   | Pretrain  
|:----------:|:-------------:|:------------------------------------------------------------------------------------------------------------------------------------------------------------------------
| UperNet | BP2MN-S | [DeiT-T]                                                                                                 
| UperNet | BP2MN-M | [DeiT-S]                                                                                               
| UperNet | BP2MN-L | [DeiT-S]                                                                                                


**COCO-Stuff-164K**

| Method  | Backbone   | Pretrain 
|:----------:|:-------------:|:------------------------------------------------------------------------------------------------------------------------------------------------------------------------
| Mask2Former | BP2MN-SL | [BEiTv2-L]                                                                                                



## Evaluation

To evaluate BP2MN-S + UperNet (512) on ADE20k val on a single node with 8 gpus run:

```shell
sh test.sh
```


## Training

To train BP2MN-S + UperNet on ADE20k on a single node with 8 gpus run:

```shell
sh train.sh
```
