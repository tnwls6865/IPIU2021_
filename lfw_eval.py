import sys
import os
import numpy as np
import cv2
import scipy.io
import copy
import core.model
import os
import torch.utils.data
from core import model, model_csp2
from dataloader.LFW_loader import LFW
from config import LFW_DATA_DIR
import argparse
import tqdm


def parseList(root):
    with open(os.path.join(root, 'lfw_test_pair.txt')) as f:
        pairs = f.read().splitlines()#[1:]
    folder_name = 'lfw-align-128'
    nameLs = []
    nameRs = []
    folds = []
    flags = []
    for i, p in enumerate(pairs):
        p = p.split(' ')
        if int(p[2]) == 1:
            nameL = os.path.join(root, folder_name, p[0])
            nameR = os.path.join(root, folder_name, p[1])
            fold = i // 600
            flag = 1
        
        else:
            nameL = os.path.join(root, folder_name, p[0])
            nameR = os.path.join(root, folder_name, p[1])
            fold = i // 600
            flag = -1

        nameLs.append(nameL)
        nameRs.append(nameR)
        folds.append(fold)
        flags.append(flag)
    return [nameLs, nameRs, folds, flags]



def getAccuracy(scores, flags, threshold):
    p = np.sum(scores[flags == 1] > threshold)
    n = np.sum(scores[flags == -1] < threshold)
    return 1.0 * (p + n) / len(scores)


def getThreshold(scores, flags, thrNum):
    accuracys = np.zeros((2 * thrNum + 1, 1))
    thresholds = np.arange(-thrNum, thrNum + 1) * 1.0 / thrNum
    for i in range(2 * thrNum + 1):
        accuracys[i] = getAccuracy(scores, flags, thresholds[i])

    max_index = np.squeeze(accuracys == np.max(accuracys))
    bestThreshold = np.mean(thresholds[max_index])
    return bestThreshold


def evaluation_10_fold(root):
    ACCs = np.zeros(10)
    result = scipy.io.loadmat(root)
    for i in range(10):
        fold = result['fold']
        flags = result['flag']
        featureLs = result['fl']
        featureRs = result['fr']

        valFold = fold != i
        testFold = fold == i
        flags = np.squeeze(flags)

        mu = np.mean(np.concatenate((featureLs[valFold[0], :], featureRs[valFold[0], :]), 0), 0)
        mu = np.expand_dims(mu, 0)
        featureLs = featureLs - mu
        featureRs = featureRs - mu
        featureLs = featureLs / np.expand_dims(np.sqrt(np.sum(np.power(featureLs, 2), 1)), 1)
        featureRs = featureRs / np.expand_dims(np.sqrt(np.sum(np.power(featureRs, 2), 1)), 1)

        scores = np.sum(np.multiply(featureLs, featureRs), 1)
        threshold = getThreshold(scores[valFold[0]], flags[valFold[0]], 10000)
        ACCs[i] = getAccuracy(scores[testFold[0]], flags[testFold[0]], threshold)

    return ACCs




def getFeatureFromTorch(lfw_dir, feature_save_dir, resume=None, gpu=True):
    net = model_csp2.MobileFacenet()
    if gpu:
        net = net.cuda()
    if resume:
        ckpt = torch.load(resume)
        net.load_state_dict(ckpt['net_state_dict']) # ['net_state_dict']
    net.eval()
    nl, nr, flods, flags = parseList(lfw_dir)
    lfw_dataset = LFW(nl, nr)
    lfw_loader = torch.utils.data.DataLoader(lfw_dataset, batch_size=32,
                                              shuffle=False, num_workers=0, drop_last=False)

    featureLs = None
    featureRs = None
    count = 0

    #progress_bar = tqdm.tqdm(lfw_loader)

    #for _, data in enumerate(tqdm.tqdm(lfw_loader)):
    for data in lfw_loader:
        if gpu:
            for i in range(len(data)):
                data[i] = data[i].cuda()
        count += data[0].size(0)
        print('extracting deep features from the face pair {}...'.format(count))
        res = [net(d).data.cpu().numpy()for d in data]
        featureL = np.concatenate((res[0], res[1]), 1)
        featureR = np.concatenate((res[2], res[3]), 1)
        if featureLs is None:
            featureLs = featureL
        else:
            featureLs = np.concatenate((featureLs, featureL), 0)
        if featureRs is None:
            featureRs = featureR
        else:
            featureRs = np.concatenate((featureRs, featureR), 0)

    result = {'fl': featureLs, 'fr': featureRs, 'fold': flods, 'flag': flags}
    scipy.io.savemat(feature_save_dir, result)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Testing')
    parser.add_argument('--lfw_dir', type=str, default=LFW_DATA_DIR, help='The path of lfw data')

    # ckpt 파일 로드
    parser.add_argument('--resume', type=str, default=r'C:\Users\pc\Desktop\PythonWorkSpace\face_rec2\MobileFaceNet_Pytorch\model\CASIA_B512_v2_20201214_223423\032.ckpt',
                        help='The path pf save model')
    parser.add_argument('--feature_save_dir', type=str, default='C:\\Users\\pc\\Desktop\\PythonWorkSpace\\face_rec2\\MobileFaceNet_Pytorch\\result\\tmp_result.mat',
                        help='The path of the extract features save, must be .mat file')
    args = parser.parse_args()


    # getFeatureFromCaffe()
    getFeatureFromTorch(args.lfw_dir, args.feature_save_dir, args.resume)
    ACCs = evaluation_10_fold(args.feature_save_dir)
    for i in range(len(ACCs)):
        print('{}    {:.2f}'.format(i+1, ACCs[i] * 100))
    print('--------')
    print('AVE    {:.2f}'.format(np.mean(ACCs) * 100))