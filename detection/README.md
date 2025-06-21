# Applying BP2MN to Object Detection

Our detection code is developed on top of [MMDetection v2.22.0](https://github.com/open-mmlab/mmdetection/tree/v2.22.0).

## Usage

Install [MMDetection v2.22.0](https://github.com/open-mmlab/mmdetection/tree/v2.22.0).

```
pip install torch==1.9.0+cu111 torchvision==0.10.0+cu111 torchaudio==0.9.0 -f https://download.pytorch.org/whl/torch_stable.html
pip install mmcv-full==1.4.2 -f https://download.openmmlab.com/mmcv/dist/cu111/torch1.9.0/index.html
pip install timm==0.4.12
pip install mmdet==2.22.0
pip install instaboostfast # for htc++
cd ops & sh make.sh # compile deformable attention
```

## Pretraining Sources

| Name          | Type       | Year | Data         | Repo                                                                                                    | Paper                                                                                                                                                                           |
| ------------- | ---------- | ---- | ------------ | ------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| DeiT          | Supervised | 2021 | ImageNet-1K  | [repo](https://github.com/facebookresearch/deit/blob/main/README_deit.md)                               | [paper](https://arxiv.org/abs/2012.12877)                                                                                                                                       |
| AugReg        | Supervised | 2021 | ImageNet-22K | [repo](https://github.com/rwightman/pytorch-image-models/blob/master/timm/models/vision_transformer.py) | [paper](https://arxiv.org/abs/2106.10270)                                                                                                                                       |
| BEiT          | MIM        | 2021 | ImageNet-22K | [repo](https://github.com/microsoft/unilm/tree/master/beit)                                             | [paper](https://arxiv.org/abs/2106.08254)                                                                                                                                       |
| MAE           | MIM        | 2021 | ImageNet-1K  | [repo](https://github.com/facebookresearch/mae)                                                         | [paper](https://arxiv.org/abs/2111.06377)                                                                                                                                       |
| Uni-Perceiver | Supervised | 2022 | Multi-Modal  | [repo](https://github.com/fundamentalvision/Uni-Perceiver)                                              | [paper](https://openaccess.thecvf.com/content/CVPR2022/papers/Zhu_Uni-Perceiver_Pre-Training_Unified_Architecture_for_Generic_Perception_for_Zero-Shot_and_CVPR_2022_paper.pdf) |
| BEiTv2        | MIM        | 2022 | ImageNet-22K | [repo](https://github.com/microsoft/unilm/tree/master/beit2)                                            | [paper](https://arxiv.org/abs/2208.06366)   |   
| DINOv2        | Self-Supervised        | 2023 | LVD-142M | [repo](https://github.com/facebookresearch/dinov2)                                            | [paper](https://arxiv.org/abs/2208.06366)     |


## Main  Models

**Mask R-CNN + DINOv2**

| Method     | Backbone      |                                                                                                                                                                                                                                                                                                                                                      
|:----------:|:-------------:|:-------------------------------------------------------------------------------------------
| Mask R-CNN | ViT-S | [DeiT-S]                                                                                            
| Mask R-CNN | BP2MN-M | [DINOv2-S]                                                                                                    
| Mask R-CNN | ViT-B | [DeiT-B]                                                                                               
| Mask R-CNN | BP2MN-L | [DINOv2-B]                                                                                                  
| Mask R-CNN | BP2MN-L | [DINOv2-B]                                                                                                  
 
 
 

**BP2MN + Co-DETR**

We combined our BP2MN with the state-of-the-art detection algorithm Co-DETR and achieved excellent results **`63.9 AP`**.

| Method     | Backbone      | Pretrain                                                                                
|:----------:|:-------------:|:----------------------------------------------------------------------------------------------
                                                                                           

## Evaluation

To evaluate Mask-RCNN + BP2MN-L on COCO val2017 on a single node with 8 gpus run:

```shell
bash test.sh
```

## Training

To train Mask-RCNN + BP2MN-L on COCO train2017 on a single node with 8 gpus for 36 epochs run:

```shell
bash train.sh
```
