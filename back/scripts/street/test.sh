CUDA_VISIBLE_DEVICES=0 python test.py --gpu_ids 0 \
  --batchSize 1 \
  --name cityscapes_test \
  --loadSize 1024 \
  --ngf 64 \
  --ImagesRoot "/disk1/yue/cityscapes/leftImg8bit_sequence_512p/" \
  --SemanticRoot "/disk1/yue/cityscapes/semantic_new/" \
  --StaticMapDir "/disk1/yue/cityscapes/dynamic_final/" \
  --InstanceRoot "/disk1/yue/cityscapes/instance_upsnet/" \
  --non_rigid_dir "/disk1/yue/cityscapes/non_rigid_mask/val/" \
  --small_object_mask_dir "/disk1/yue/cityscapes/small_object_mask/val/" \
  --load_pretrain "./checkpoints/cityscapes/" \
  --how_many 1000