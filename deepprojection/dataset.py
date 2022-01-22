#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Load PyTorch
import torch
from torch.utils.data import Dataset

# Load LCLS data management and LCLS data access (through detector) module
import psana

# Load misc modules
import numpy as np
import random
import json
import csv
import os


class SPIImg(Dataset):
    """
    Single particle imaging (SPI) dataset.

    It loads SPI images and labels for machine learning with PyTorch, hence a
    data loader.  A label file, which contains the label of every image , is
    needed for a successful data loading.  
    """

    def __init__(self, fl_csv):
        """
        Args:
            fl_csv (string) : CSV file of datasets.
        """
        self.dataset_dict  = {}
        self.imglabel_list = []
        self.psana_imgreader_dict = {}

        # Read csv file of datasets
        with open(fl_csv, 'r') as fh:
            lines = csv.reader(fh)

            # Skip the header
            next(lines)

            # Read each line/dataset
            for line in lines:
                # Fetch metadata of a dataset 
                exp, run, mode, detector_name, drc_root = line

                # Form a minimal basename to describe a dataset
                basename = f"{exp}.{run}"

                # Initiate image accessing layer
                self.psana_imgreader_dict[basename] = PsanaImg(exp, run, mode, detector_name)

                # Obtain image labels from this dataset
                imglabel_fileparser       = ImgLabelFileParser(exp, run, drc_root)
                self.dataset_dict[basename] = imglabel_fileparser.imglabel_dict

        # Enumerate each image from all datasets
        for dataset_id, dataset_content in self.dataset_dict.items():
            # Get the exp and run
            exp, run = dataset_id.split(".")

            for event_num, label in dataset_content.items():
                self.imglabel_list.append( (exp, run, int(event_num), int(label)) )

        return None


    def __len__(self):
        return len(self.imglabel_list)


    def __getitem__(self, idx):
        exp, run, event_num, label = self.imglabel_list[idx]

        print(f"Loading image {exp}.{run}.{event_num}...")

        basename = f"{exp}.{run}"
        img = self.psana_imgreader_dict[basename].get(int(event_num))

        return img.reshape(-1), int(label)


    def get_imagesize(self, idx):
        exp, run, event_num, label = self.imglabel_list[idx]

        print(f"Loading image {exp}.{run}.{event_num}...")

        basename = f"{exp}.{run}"
        img = self.psana_imgreader_dict[basename].get(int(event_num))

        return img.shape


class SPIImgDataset(SPIImg):
    """
    Siamese requires an input of three images at a time, namely anchor,
    positive, and negative.  This dataset will create such triplet
    automatically by randomly choosing an anchor followed up by randomly
    selecting a positive and negative, respectively.
    """
    def __init__(self, fl_csv, size_sample, seed):
        super().__init__(fl_csv)

        self.num_stockimgs = len(self.imglabel_list)
        self.size_sample = size_sample
        self.seed = seed

        # Create a lookup table for sequence number (seqi) based on label
        self.label_seqi_dict = {}
        for seqi, (_, _, _, label) in enumerate(self.imglabel_list):
            if not label in self.label_seqi_dict: self.label_seqi_dict[label] = [seqi]
            else: self.label_seqi_dict[label].append(seqi)

        return None

    def __len__(self):
        return self.size_sample

    def __getitem__(self, idx):
        if idx >= self.size_sample: raise IndexError("Index is larger than the size of samples.")

        random.seed(self.seed)

        # Randomly select an anchor
        anchor_bucket = range(self.num_stockimgs)
        id_anchor     = random.sample(anchor_bucket, 1)[0]

        # Read the anchor image
        img_anchor, label_anchor = super().__getitem__(id_anchor)

        # Create buckets of positives according to the anchor
        pos_bucket = self.label_seqi_dict[label_anchor]

        # Create buckets of negatives according to the anchor
        neg_bucket = []
        for label, ids in self.label_seqi_dict.items(): 
            if label == label_anchor: continue
            neg_bucket += ids

        # Randomly sample one positive and one negative
        id_pos = random.sample(pos_bucket, 1)[0]
        id_neg = random.sample(neg_bucket, 1)[0]

        # Read positive and negative images
        img_pos, _ = super().__getitem__(id_pos)
        img_neg, _ = super().__getitem__(id_neg)

        return img_anchor, img_pos, img_neg, label_anchor


class ImgLabelFileParser:
    """
    It parses a label file associated with a run in an experiment.  The label 
    file, a json file of event number and labels, should be generated by
    psocake.  This parser numerically sorts the event number and assign a
    zero-based index to each event number.  This is implemented primarily for
    complying with PyTorch DataLoader.  
    """

    def __init__(self, exp, run, drc_root):
        self.exp                   = exp
        self.run                   = run
        self.drc_root              = drc_root
        self.path_labelfile        = ""
        self.imglabel_dict = {}

        # Initialize indexed image label
        self._load_imglabel()

        return None


    def __getitem__(self, idx):
        return self.indexed_imglabel_dict[idx]


    def _locate_labelfile(self):
        # Get the username
        username = os.environ.get("USER")

        # The prefix directory to find label file
        drc_run     = f"r{int(self.run):04d}"
        drc_psocake = os.path.join(self.exp, username, 'psocake', drc_run)

        # Basename of a label file
        basename = f"{self.exp}_{int(self.run):04d}"

        # Locate the path to label file
        fl_json = f"{basename}.label.json"
        path_labelfile = os.path.join(self.drc_root, drc_psocake, fl_json)

        return path_labelfile


    def _load_imglabel(self):
        # Load path to the label file
        self.path_labelfile = self._locate_labelfile()

        # Read, sort and index labels
        if os.path.exists(self.path_labelfile):
            # Read label
            with open(self.path_labelfile, 'r') as fh:
                imglabel_dict = json.load(fh)

            # Sort label
            self.imglabel_dict = dict( sorted( imglabel_dict.items(), key = lambda x:int(x[0]) ) )

        else:
            print(f"File doesn't exist!!! Missing {self.path_labelfile}.")

        return None


class PsanaImg:
    """
    It serves as an image accessing layer based on the data management system
    psana in LCLS.  
    """

    def __init__(self, exp, run, mode, detector_name):
        # Biolerplate code to access an image
        # Set up data source
        self.datasource_id = f"exp={exp}:run={run}:{mode}"
        self.datasource    = psana.DataSource( self.datasource_id )
        self.run_current   = next(self.datasource.runs())
        self.timestamps    = self.run_current.times()

        # Set up detector
        self.detector = psana.Detector(detector_name)


    def get(self, event_num):
        # Fetch the timestamp according to event number
        timestamp = self.timestamps[int(event_num)]

        # Access each event based on timestamp
        event = self.run_current.event(timestamp)

        # Fetch image data based on timestamp from detector
        img = self.detector.image(event)

        return img
