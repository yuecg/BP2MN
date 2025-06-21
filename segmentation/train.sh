kill -9 $(lsof -t /dev/nvidia*)
sleep 1s

# bp2mn-small
sh dist_train.sh configs/ade20k/upernet_bp2mn_small_512_160k_ade20k.py 8 --seed 2023

# bp2mn-medium
sh dist_train.sh configs/ade20k/upernet_bp2mn_medium_512_160k_ade20k.py 8 --seed 2023

# bp2mn-large
sh dist_train.sh configs/ade20k/upernet_bp2mn_large_512_160k_ade20k.py 8 --seed 2023


