kill -9 $(lsof -t /dev/nvidia*)
sleep 1s
bash dist_test.sh configs/mask_rcnn/dinov2/mask_rcnn_dinov2_bp2mn_base_fpn_3x_coco.py mask_rcnn_dinov2_bp2mn_large_3x.pth 8 --eval bbox