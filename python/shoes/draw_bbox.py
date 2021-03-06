# -*- coding:UTF-8 -*-
import numpy as np
from PIL import Image
from collections import Counter
from multiprocessing import Pool
import os, sys, argparse, time, cv2
# import imutils, profile

# python python/shoes/draw_bbox.py -i data/shoes

outmark = 'img'

def get_file_list(input_root):
    input_img_dir  = os.path.join(input_root, outmark)
    output_img_dir = os.path.join(input_root, outmark + '_box')
    output_txt_dir = os.path.join(input_root, outmark + '_labels')

    if not os.path.exists(output_img_dir):
        os.mkdir(output_img_dir)   
    if not os.path.exists(output_txt_dir):
        os.mkdir(output_txt_dir)     

    input_img_list = []
    output_img_list = []
    output_txt_list = []
    fo = open(input_root + '/' + outmark +'.txt', 'w')
    for img_file in os.listdir(input_img_dir):
        if img_file.endswith('.jpg'):
            input_img_file = os.path.join(input_img_dir, img_file)
            output_img_file = os.path.join(output_img_dir, img_file)
            output_txt_file = os.path.join(output_txt_dir, img_file.replace('jpg', 'txt'))
            input_img_list.append(input_img_file)
            output_img_list.append(output_img_file)
            output_txt_list.append(output_txt_file)
            fo.write(input_img_file+'\n')
    fo.close()
    
    return input_img_list, output_img_list, output_txt_list

def draw_bbox((input_img_file, output_img_file, output_txt_file)):
    print input_img_file
    img = cv2.imread(input_img_file)

    # resize img to fit_img
    raw_w, raw_h = img.shape[1], img.shape[0]
    size = 300
    if raw_w >= raw_h:
        fit_w = int(float(size)*raw_w/raw_h)   
        fit_h = size
    else:
        fit_h = int(float(size)*raw_h/raw_w) 
        fit_w = size  
    fit_img = cv2.resize(img, (fit_w, fit_h), interpolation = cv2.INTER_LINEAR)

    # get fit_bbox
    left, top, right, bottom = get_bbox(fit_img, fit_w, fit_h)
    
    # resize fit_bbox to bbox
    left = int(float(left)*raw_w/fit_w)
    top = int(float(top)*raw_h/fit_h)
    right = int(float(right)*raw_w/fit_w)
    bottom = int(float(bottom)*raw_h/fit_h)
    
    # draw bbox
    cv2.rectangle(img, (left, top), (right, bottom), (0, 255, 0), 2)
    cv2.imwrite(output_img_file, img)
    
    # output bbox to txt
    x = (left + right)/2.0
    y = (top + bottom)/2.0
    w = right - left
    h = bottom - top
    x, y, w, h = x/raw_w, y/raw_h, w*1.0/raw_w, h*1.0/raw_h
    line = np.array([[0, x, y, w, h]])
    np.savetxt(output_txt_file, line, fmt="%d %f %f %f %f")
    
def get_bbox(fit_img, fit_w, fit_h):
    # canny for bbox
    grayed = cv2.cvtColor(fit_img, cv2.COLOR_BGR2GRAY)
    grayed = cv2.GaussianBlur(grayed, (5, 5), 0)
    pix = np.mean([grayed[0, 0], grayed[0, fit_w/2], grayed[0, fit_w-1], \
        grayed[fit_h/2, 0], grayed[fit_h/2, fit_w-1], \
        grayed[fit_h-1, 0], grayed[fit_h-1, fit_w/2], grayed[fit_h-1, fit_w-1]])
    pix = 255 - int(pix)
    # 这个阈值告诉算法“什么程度的边界才算边缘”，阈值越大表示标准越严厉，提取到的边缘越少
    canny_img = cv2.Canny(grayed, pix + 5, pix + 35) 
    if np.max(canny_img) == 0:
        top    = 0
        right  = fit_w - 1
        bottom = fit_h - 1
        left   = 0
    else:
        linepix = np.where(canny_img == 255)
        top    = min(linepix[0])
        right  = max(linepix[1])
        bottom = max(linepix[0])
        left   = min(linepix[1])

    # grabcut for mask
    mask = np.zeros((fit_h, fit_w), np.uint8)
    bgdModel = np.zeros((1, 65), np.float64)
    fgdModel = np.zeros((1, 65), np.float64)
    rect = (left, top, right - left, bottom - top) 
    cv2.grabCut(fit_img, mask, rect, bgdModel, fgdModel, 3, cv2.GC_INIT_WITH_RECT)
    mask2 = np.where((mask==0)|(mask==2), 0, 1).astype('uint8')
    
    # get binary img with mask
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    th3 = cv2.dilate(canny_img, kernel)
    bin_img = cv2.bitwise_and(th3, th3, mask = mask2)
    
    # findContours for final bbox
    contours, dummy = cv2.findContours(bin_img.copy(), cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE) 
    contours = sorted(contours, key = cv2.contourArea, reverse = True)
    if len(contours) > 0:
        box0 = cv2.boundingRect(contours[0])
        left = box0[0]
        top = box0[1]
        right = box0[0] + box0[2]
        bottom = box0[1] + box0[3]
        if len(contours) > 1:
            box1 = cv2.boundingRect(contours[1])
            if (box1[2]*box1[3]*1.0)/(box0[2]*box0[3]) >= 0.4:
                left = min(box0[0], box1[0])
                top = min(box0[1], box1[1])
                right = max(box0[0]+box0[2], box1[0]+box1[2])
                bottom = max(box0[1]+box0[3], box1[1]+box1[3])
    return left, top, right, bottom

def get_args():
    parser = argparse.ArgumentParser(description = 'draw the bbox of images')
    parser.add_argument('-i', dest = 'input_root',
        help = 'input root of images and labels', default = None, type = str)
    parser.add_argument('-c', dest = 'cpu_num',
        help = 'cpu number for multiprocessing', default = 16, type = int)
    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(1)
    args = parser.parse_args()
    return args

if __name__ == "__main__":

    tic = time.time()

    args = get_args()
    input_root = args.input_root
    cpu_num = args.cpu_num

    input_img_list, output_img_list, output_txt_list = get_file_list(input_root)
    
    pool = Pool(cpu_num)
    pool.map(draw_bbox, zip(input_img_list, output_img_list, output_txt_list))
    '''
    for argms in zip(input_img_list, output_img_list, output_txt_list):
        draw_bbox(argms)
    '''
    toc = time.time()
    print 'running time: {} seconds'.format(toc-tic)

