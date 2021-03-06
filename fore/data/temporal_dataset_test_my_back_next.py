import os.path
import random, glob
import torch
from data.base_dataset import BaseDataset, get_img_params, get_transform
from PIL import Image
import numpy as np
from torch.autograd import Variable
import cv2

def compute_bbox(mask):
    '''
    :param mask: mask of size(height, width)
    :return: bbox
    '''
    y, x  = np.where(mask == 1)
    if len(x) == 0 or len(y) == 0:
        return None
    bbox = np.zeros((2,2))
    bbox[:,0] = [np.min(x),np.min(y)]
    bbox[:,1] = [np.max(x),np.max(y)]
    return bbox

def transfrom_single_image(arr):
    src_index = [7, 8, 11, 12, 13, 17, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 31, 32, 33]
    dst_index = [0, 1, 2,  3,  4,  5,  6,  7,  8,  9,  10, 11, 12, 13, 14, 15, 16, 17, 18]
    dst_arr = np.zeros_like(arr)
    for i in range(len(src_index)):
        dst_arr[arr == src_index[i]] = dst_index[i]
    return dst_arr


class TestTemporalDataset(BaseDataset):
    # Load pre-computed optical flow to save gpu memory
    def initialize(self, opt, flownet):
        self.opt = opt
        #self.height = int(opt.loadSize/2.0)
        #self.width = opt.loadSize
        self.height = 512
        self.width  = 1024
        #if opt.isTrain == True:
        #    self.phase = 'train'
        #else:
        self.phase = 'val'
        self.flownet = flownet
        self.tIn = opt.tIn
        self.tOut = opt.tOut
        self.mask_threshold = int(0.002 * self.height * self.width)
        self.all_image_paths = self.load_all_image_paths(opt.npy_dir)

        # Load predicted 5 background and foreground
        self.my_back_root = "./result/cityscapes/"
        self.n_of_seqs = len(self.all_image_paths)                 # number of sequences to train
        print("Testing number of video paths = %d"%self.n_of_seqs)

    def __getitem__(self, index):
        cnt_info = np.load(self.all_image_paths[index], allow_pickle=True)
        videoid = cnt_info[6]
        tIn = self.opt.tIn
        tOut = self.opt.tOut
        n_gpu = len(self.opt.gpu_ids)
        tAll = tIn + tOut
        depth_paths = cnt_info[3]
        params = get_img_params(self.opt, (self.width, self.height))
        t_bic = get_transform(self.opt, params)
        t_ner = get_transform(self.opt, params, Image.NEAREST, normalize=False)
        cnt_back_dir = self.my_back_root + "%04d/"%(videoid)
        
        # Load predict semantic, background, image, and depth
        Semantics = torch.cat([self.get_semantic(cnt_back_dir + "fore_complete_%02d_gray.png"%p, t_ner, is_label=True) for p in range(1,5)], dim=0)
        Backs = torch.cat([self.get_image(cnt_back_dir + "warp_image_bwd_inpainted_%02d.png"%p, t_bic) for p in range(1, 10)], dim=0)
        Images = torch.cat([self.get_image(cnt_back_dir + "fore_complete_%02d.png"%p, t_bic) for p in range(1, 5)], dim=0)
        Depths = torch.cat([torch.from_numpy(np.expand_dims(np.load(depth_paths[p]), axis=0)) for p in range(tIn)], dim=0)
        # Load Necessary information for all objects and transform to tensor

        Masks = 0
        Combines = 0
        LastObjects = 0
        LastMasks = 0
        Classes = 0
        OriginMasks = 0

        ### find dirs
        all_files = os.listdir(cnt_back_dir)
        all_files.sort()
        dirs = []
        for k in all_files:
            if os.path.isdir(cnt_back_dir + k):
                dirs.append(cnt_back_dir + k + "/")
        print(dirs)

        for k in range(len(dirs)):
            cnt_object_dir = dirs[k]
            f = open(cnt_object_dir + "class.txt", 'r')
            cl = int(f.readlines()[0][:-1])
            cnt_origin_mask = t_ner(Image.open(cnt_object_dir + "input_mask_03.png"))
            OriginMasks = cnt_origin_mask if OriginMasks is 0 else torch.cat([OriginMasks, cnt_origin_mask], dim=0)
            cnt_mask_seq, cnt_combine_seq, cnt_last_object, cnt_last_mask = self.gen_combine_seq(cnt_object_dir, t_ner, t_bic)                     
            Masks = cnt_mask_seq if Masks is 0 else torch.cat([Masks, cnt_mask_seq], dim=0)
            Combines = cnt_combine_seq if Combines is 0 else torch.cat([Combines, cnt_combine_seq], dim=0)
            LastObjects = cnt_last_object if LastObjects is 0 else torch.cat([LastObjects, cnt_last_object], dim=0)
            cnt_class = torch.from_numpy(np.array([cl]))
            Classes = cnt_class if Classes is 0 else torch.cat([Classes, cnt_class], dim = 0)
            LastMasks = cnt_last_mask if LastMasks is 0 else torch.cat([LastMasks, cnt_last_mask], dim=0)


        return_list = {'Image': Images, 'Back': Backs, 'Mask': Masks, 'Semantic': Semantics, \
        'Combine': Combines, 'LastObject': LastObjects, 'Depths': Depths, \
        'Classes': Classes, 'LastMasks': LastMasks, 'OriginMasks': OriginMasks, 'VideoId': videoid}
        return return_list

    def gen_combine_seq(self, cnt_object_dir, t_ner, t_bic):
        cnt_Masks = 0
        cnt_Combines = 0
        for i in range(self.tIn):
            cnt_Maski = t_ner(Image.open(cnt_object_dir + "pred_mask_%02d.png"%i))#0-1->0-1/255
            cnt_Combinei = t_bic(Image.open(cnt_object_dir + "pred_complete_%02d.png"%i))
            cnt_Masks = cnt_Maski if i == 0 else torch.cat([cnt_Masks, cnt_Maski], dim=0)
            cnt_Combines = cnt_Combinei if i == 0 else torch.cat([cnt_Combines, cnt_Combinei], dim=0)
        last_image = np.array(Image.open(cnt_object_dir + "pred_complete_04.png"))
        last_mask = np.array(Image.open(cnt_object_dir + "pred_mask_04.png"))/255
        kernel_1 = np.ones((2,2), np.uint8)
        last_mask_1 = cv2.dilate(last_mask.astype(np.float32), kernel_1, iterations=1)
        last_object = last_image * np.tile(np.expand_dims(last_mask_1, axis=2), [1,1,3])
        LastObject = t_bic(Image.fromarray(last_object.astype(np.uint8)))
        LastMask = t_ner(Image.open(cnt_object_dir + "pred_mask_04.png"))
        return cnt_Masks, cnt_Combines, LastObject, LastMask

    def mask2bbox(self, mask):
        y, x = np.where(mask == 1)
        min_y = np.min(y)
        max_y = np.max(y)
        min_x = np.min(x)
        max_x = np.max(x)
        center_x = min_x + (max_x - min_x)/2.0
        center_y = min_y + (max_y - min_y)/2.0
        return center_x, center_y

    def get_image(self, A_path, transform_scaleA, is_label=False):
        #print(A_path)
        A_img = Image.open(A_path)
        A_scaled = transform_scaleA(A_img)
        if is_label:
            A_scaled *= 255
        return A_scaled

    def get_semantic(self, A_path, transform_scaleA, is_label=False):
        A_img = Image.open(A_path)
        transformed_A = Image.fromarray(transfrom_single_image(np.array(A_img)).astype(np.uint8))
        A_scaled = transform_scaleA(transformed_A)
        if is_label:
            A_scaled *= 255
        return A_scaled


    def __len__(self):
        return self.n_of_seqs

    def name(self):
        return 'TestTemporalDataset'

    def load_all_image_paths(self, path):
        npy_files = sorted(glob.glob(path + "*.npy"))
        return npy_files
        
    def LoadDepthDataSample(self, DepthRoot, images):
        tmp = []
        for p in range(self.tIn):
            curr_full = images[p]
            split_name = curr_full.split("/")
            depth_path = os.path.join(DepthRoot, split_name[-3],split_name[-2],split_name[-1])
            depth_path = depth_path[:-3] + "npy"
            tmp.append(scipy.misc.imresize(np.load(depth_path),(self.h, self.w)))
        Depth = np.concatenate([np.expand_dims(np.expand_dims(tmp[q], 0), 3) for q in range(self.tIn)],axis=3)
        # Depth may be zero, compute average value then 1/average depth
        return Depth

    def IOU_mask(self, mask_A, mask_B):
        #semantic instance,
        mask_A = mask_A.astype(np.bool)
        mask_B = mask_B.astype(np.bool)
        return 1.0 * (mask_A & mask_B).astype(np.int32).sum() / mask_B.astype(np.int32).sum()


    def load_object_mask_val(self, instance_mask_list, images, depth):
        '''
        :param instance: instance contains gt instance or
        :param semantic:
        :param depth:
        :param curr_image:
        :param gt_flag:
        :return:
        '''
        opt = self.opt
        segs = []
        
        for j in range(len(instance_mask_list)):
            #print(instance_mask_list[j])
            cnt_info = []
            flag = True
            for k in range(self.tIn):
                cnt_mask = np.array(Image.open(instance_mask_list[j][k]).resize((self.sp*2, self.sp), resample=Image.NEAREST))/255
                cnt_mask_expand = expand_dims_2(cnt_mask)
                cnt_bbox = compute_bbox(cnt_mask)
                if cnt_bbox is None:
                    continue
                big_bbox = self.enlarge_bbox(cnt_bbox)
                big_mask = self.bbox2mask(big_bbox)
                cnt_bbox_mask = self.bbox2mask(cnt_bbox)
                cnt_depth = np.mean(cnt_mask_expand * self.depthInput[:,:,:,k:k+1])
                cnt_color_image = np.tile(cnt_mask_expand, [1, 1, 1, 3]) * images[:,:,:,k*3:(k+1)*3]
                #scipy.misc.imsave("./debug/segs_%d.png" % j, cnt_color_image[0, :, :, :])
                big_image = np.tile(expand_dims_2(big_mask), [1, 1, 1, 3]) * images[:,:,:,k*3:(k+1)*3]
                cnt_info.append(
                        (cnt_mask, cnt_color_image[0, :, :, :], cnt_depth, cnt_bbox, big_image[0, :, :, :]))
            if len(cnt_info) > 0:
                segs.append(cnt_info)
        return segs


    def preprocess_bike_person(self, instance_list):
        valid_index = np.zeros(len(instance_list)) + 1
        # classes
        #'person'-1, 'bicycle'-2, 'car'-3, 'motorcycle'-4,'bus'-6, 'train'-7, 'truck'-8
        valid_class = [1,2,3,4,6,7,8]
        mask_all = []
        for i in range(len(instance_list)):
            if valid_index[i] == 0:
                continue
            curr_list = instance_list[i]
            if curr_list['class_id'] not in valid_class:
                continue
            if curr_list['class_id'] == 2 or curr_list['class_id'] == 4:
                iou_score = -1
                person_id = -1
                bbox_bike = curr_list['bbox']
                bbox_mask_bike = bbox2mask_maskrcnn(bbox_bike)
                for j in range(len(instance_list)):
                    if valid_index[j] == 1:
                        if instance_list[j]['class_id'] == 1:
                            bbox_person = instance_list[j]['bbox']
                            bbox_mask_person = bbox2mask_maskrcnn(bbox_person)
                            iou = self.IOU_mask(bbox_mask_bike, bbox_mask_person)
                            if iou > iou_score:
                                iou_score = iou
                                person_id = j
                if iou_score > 0:
                    mask_all.append(((curr_list['mask'] | instance_list[person_id]['mask']), 9))
                    valid_index[i] = 0
                    valid_index[person_id] = 0
        for k in range(len(instance_list)):
            if valid_index[k] == 1 and instance_list[k]['class_id'] in valid_class:
                mask_all.append((instance_list[k]['mask'], instance_list[k]['class_id']))
        return mask_all

    def enlarge_bbox(self, bbox):
        '''
        bbox[:, 0] = [np.min(x), np.min(y)]
        bbox[:, 1] = [np.max(x), np.max(y)]
        bbox [min_x, max_x]
             [min_y, max_y]
        '''
        # enlarge bbox to avoid any black boundary
        if self.opt.sp == 256:
            gap = 2
        elif self.opt.sp == 512:
            gap = 4
        elif self.opt.sp == 1024:
            gap = 8
        bbox[0,0] = np.maximum(bbox[0,0] - gap, 0)
        bbox[1,0] = np.maximum(bbox[1,0] - gap, 0)
        bbox[0,1] = np.minimum(bbox[0,1] + gap, self.w-1)
        bbox[1,1] = np.minimum(bbox[1,1] + gap, self.h-1)
        return bbox

    def bbox2mask(self, bbox):
        mask = np.zeros((self.h, self.w))
        bbox = bbox.astype(np.int32)
        mask[bbox[1,0]:bbox[1,1]+1,bbox[0,0]:bbox[0,1]+1] = 1
        return mask
