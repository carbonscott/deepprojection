#!/usr/bin/env python
# -*- coding: utf-8 -*-

import torch
import torch.nn as nn

import logging

logger = logging.getLogger(__name__)

class ConfigSiameseModel:
    alpha   = 0.5

    def __init__(self, **kwargs):
        logger.info(f"___/ Configure Siamese Model \___")

        # Set values of attributes that are not known when obj is created
        for k, v in kwargs.items():
            setattr(self, k, v)
            logger.info(f"KV - {k:16} : {v}")


class SiameseModel(nn.Module):
    """ Embedding independent triplet loss. """

    def __init__(self, config):
        super().__init__()
        self.alpha   = config.alpha
        self.encoder = config.encoder


    def forward(self, img_anchor, img_pos, img_neg):
        # Encode images...
        img_anchor_embed = self.encoder.encode(img_anchor)
        img_pos_embed    = self.encoder.encode(img_pos)
        img_neg_embed    = self.encoder.encode(img_neg)

        # Calculate the RMSD between anchor and positive...
        # Well, it's in fact squared distance
        img_diff = img_anchor_embed - img_pos_embed
        rmsd_anchor_pos = torch.sum(img_diff * img_diff, dim = -1)

        # Calculate the RMSD between anchor and negative...
        img_diff = img_anchor_embed - img_neg_embed
        rmsd_anchor_neg = torch.sum(img_diff * img_diff, dim = -1)

        # Calculate the triplet loss, relu is another implementation of max(a, b)...
        loss_triplet = torch.relu(rmsd_anchor_pos - rmsd_anchor_neg + self.alpha)

        return img_anchor_embed, img_pos_embed, img_neg_embed, loss_triplet.mean()


    def configure_optimizers(self, config_train):
        optimizer = torch.optim.Adam(self.encoder.parameters(), lr = config_train.lr)
        ## optimizer = torch.optim.SGD(self.encoder.parameters(), lr = config_train.lr)

        return optimizer




class SiameseModelCompare(nn.Module):
    """ Embedding independent triplet loss. """

    def __init__(self, config):
        super().__init__()
        self.encoder = config.encoder


    def forward(self, img_anchor, img_second):
        # Encode images...
        img_anchor_embed = self.encoder.encode(img_anchor)
        img_second_embed = self.encoder.encode(img_second)

        # Calculate the RMSD between anchor and second...
        img_diff           = img_anchor_embed - img_second_embed
        rmsd_anchor_second = torch.sum(img_diff * img_diff, dim = -1)

        return img_anchor_embed, img_second_embed, rmsd_anchor_second.mean()




class SimpleEmbedding(nn.Module):
    """ Embedding independent triplet loss. """

    def __init__(self, config):
        super().__init__()
        self.encoder = config.encoder


    def forward(self, img):
        return self.encoder.encode(img)
