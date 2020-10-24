CUDA_VISIBLE_DEVICES=7 python test.py \
  --gpu_ids 0 \
  --batchSize 1 \
  --static \
  --name kitti_test \
  --dataset 'kitti' \
  --ngf 64 \
  --loadSize 256 \
  --tOut 3 \
  --ImagesRoot "/disk1/yue/kitti/raw_data/" \
  --SemanticRoot "/disk1/yue/kitti/semantic/" \
  --StaticMapDir "/disk1/yue/kitti/dynamic_10.22/" \
  --InstanceRoot "/disk1/yue/kitti/instance/" \
  --non_rigid_dir "/disk1/yue/kitti/non_rigid_mask/val/" \
  --small_object_mask_dir "/disk1/yue/kitti/small_object_mask/val/" \
  --load_pretrain "./checkpoints/kitti/" \
  --how_many 2000