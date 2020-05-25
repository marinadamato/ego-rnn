import random
import math
import numbers
import collections
import numpy as np
import torch
from PIL import Image, ImageOps
try:
    import accimage
except ImportError:
    accimage = None


class Compose(object):
    """Composes several transforms together.
    Args:
        transforms (list of ``Transform`` objects): list of transforms to compose.
    Example:
        >>> transforms.Compose([
        >>>     transforms.CenterCrop(10),
        >>>     transforms.ToTensor(),
        >>> ])
    """

    def __init__(self, transforms):
        self.transforms = transforms

    def __call__(self, img, inv=False, flow=False):
        for t in self.transforms:
            img = t(img, inv, flow)
        return img

    def randomize_parameters(self):
        for t in self.transforms:
            t.randomize_parameters()


class ToTensor(object):
    """Convert a ``PIL.Image`` or ``numpy.ndarray`` to tensor.
    Converts a PIL.Image or numpy.ndarray (H x W x C) in the range
    [0, 255] to a torch.FloatTensor of shape (C x H x W) in the range [0.0, 1.0].
    """

    def __init__(self, norm_value=255):
        self.norm_value = norm_value

    def __call__(self, pic, inv, flow):
        """
        Args:
            pic (PIL.Image or numpy.ndarray): Image to be converted to tensor.
        Returns:
            Tensor: Converted image.
        """
        if isinstance(pic, np.ndarray):
            # handle numpy array
            img = torch.from_numpy(pic.transpose((2, 0, 1)))
            # backward compatibility
            return img.float().div(self.norm_value)

        if accimage is not None and isinstance(pic, accimage.Image):
            nppic = np.zeros([pic.channels, pic.height, pic.width], dtype=np.float32)
            pic.copyto(nppic)
            return torch.from_numpy(nppic)

        # handle PIL Image
        if pic.mode == 'I':
            img = torch.from_numpy(np.array(pic, np.int32, copy=False))
        elif pic.mode == 'I;16':
            img = torch.from_numpy(np.array(pic, np.int16, copy=False))
        else:
            img = torch.ByteTensor(torch.ByteStorage.from_buffer(pic.tobytes()))
        # PIL image mode: 1, L, P, I, F, RGB, YCbCr, RGBA, CMYK
        if pic.mode == 'YCbCr':
            nchannel = 3
        elif pic.mode == 'I;16':
            nchannel = 1
        else:
            nchannel = len(pic.mode)
        img = img.view(pic.size[1], pic.size[0], nchannel)
        # put it from HWC to CHW format
        # yikes, this transpose takes 80% of the loading time/CPU
        img = img.transpose(0, 1).transpose(0, 2).contiguous()
        if isinstance(img, torch.ByteTensor):
            return img.float().div(self.norm_value)
        else:
            return img

    def randomize_parameters(self):
        pass


class Normalize(object):
    """Normalize an tensor image with mean and standard deviation.
    Given mean: (R, G, B) and std: (R, G, B),
    will normalize each channel of the torch.*Tensor, i.e.
    channel = (channel - mean) / std
    Args:
        mean (sequence): Sequence of means for R, G, B channels respecitvely.
        std (sequence): Sequence of standard deviations for R, G, B channels
            respecitvely.
    """

    def __init__(self, mean, std):
        self.mean = mean
        self.std = std

    def __call__(self, tensor, inv, flow):
        """
        Args:
            tensor (Tensor): Tensor image of size (C, H, W) to be normalized.
        Returns:
            Tensor: Normalized image.
        """
        # TODO: make efficient
        if flow is True:
            mean = [np.mean(self.mean)]
            std = [np.mean(self.std)]
        else:
            mean = self.mean
            std = self.std
        for t, m, s in zip(tensor, mean, std):
            t.sub_(m).div_(s)
        return tensor

    def randomize_parameters(self):
        pass


class Scale(object):
    """Rescale the input PIL.Image to the given size.
    Args:
        size (sequence or int): Desired output size. If size is a sequence like
            (w, h), output size will be matched to this. If size is an int,
            smaller edge of the image will be matched to this number.
            i.e, if height > width, then image will be rescaled to
            (size * height / width, size)
        interpolation (int, optional): Desired interpolation. Default is
            ``PIL.Image.BILINEAR``
    """

    def __init__(self, size, interpolation=Image.BILINEAR):
        assert isinstance(size, int) or (isinstance(size, collections.Iterable) and len(size) == 2)
        self.size = size
        self.interpolation = interpolation

    def __call__(self, img, inv, flow):
        """
        Args:
            img (PIL.Image): Image to be scaled.
        Returns:
            PIL.Image: Rescaled image.
        """
        if isinstance(self.size, int):
            w, h = img.size
            if (w <= h and w == self.size) or (h <= w and h == self.size):
                return img
            if w < h:
                ow = self.size
                oh = int(self.size * h / w)
                return img.resize((ow, oh), self.interpolation)
            else:
                oh = self.size
                ow = int(self.size * w / h)
                return img.resize((ow, oh), self.interpolation)
        else:
            return img.resize(self.size, self.interpolation)

    def randomize_parameters(self):
        pass


class CenterCrop(object):
    """Crops the given PIL.Image at the center.
    Args:
        size (sequence or int): Desired output size of the crop. If size is an
            int instead of sequence like (h, w), a square crop (size, size) is
            made.
    """

    def __init__(self, size):
        if isinstance(size, numbers.Number):
            self.size = (int(size), int(size))
        else:
            self.size = size

    def __call__(self, img, inv, flow):
        """
        Args:
            img (PIL.Image): Image to be cropped.
        Returns:
            PIL.Image: Cropped image.
        """
        w, h = img.size
        th, tw = self.size
        x1 = int(round((w - tw) / 2.))
        y1 = int(round((h - th) / 2.))
        return img.crop((x1, y1, x1 + tw, y1 + th))

    def randomize_parameters(self):
        pass


class RandomHorizontalFlip(object):
    """Horizontally flip the given PIL.Image randomly with a probability of 0.5."""

    def __call__(self, img, inv, flow):
        """
        Args:
            img (PIL.Image): Image to be flipped.
        Returns:
            PIL.Image: Randomly flipped image.
        """
        if self.p < 0.5:
            img =  img.transpose(Image.FLIP_LEFT_RIGHT)
            if inv is True:
                img = ImageOps.invert(img)
        return img

    def randomize_parameters(self):
        self.p = random.random()


class MultiScaleCornerCrop(object):
    """Crop the given PIL.Image to randomly selected size.
    A crop of size is selected from scales of the original size.
    A position of cropping is randomly selected from 4 corners and 1 center.
    This crop is finally resized to given size.
    Args:
        scales: cropping scales of the original size
        size: size of the smaller edge
        interpolation: Default: PIL.Image.BILINEAR
    """

    def __init__(self, scales, size, interpolation=Image.BILINEAR):
        self.scales = scales
        self.size = size
        self.interpolation = interpolation

        self.crop_positions = ['c', 'tl', 'tr', 'bl', 'br']

    def __call__(self, img, inv, flow):
        # print(img.size[0])
        min_length = min(img.size[0], img.size[1])
        crop_size = int(min_length * self.scale)

        image_width = img.size[0]
        image_height = img.size[1]

        if self.crop_position == 'c':
            center_x = image_width // 2
            center_y = image_height // 2
            box_half = crop_size // 2
            x1 = center_x - box_half
            y1 = center_y - box_half
            x2 = center_x + box_half
            y2 = center_y + box_half
        elif self.crop_position == 'tl':
            x1 = 0
            y1 = 0
            x2 = crop_size
            y2 = crop_size
        elif self.crop_position == 'tr':
            x1 = image_width - crop_size
            y1 = 1
            x2 = image_width
            y2 = crop_size
        elif self.crop_position == 'bl':
            x1 = 1
            y1 = image_height - crop_size
            x2 = crop_size
            y2 = image_height
        elif self.crop_position == 'br':
            x1 = image_width - crop_size
            y1 = image_height - crop_size
            x2 = image_width
            y2 = image_height

        img = img.crop((x1, y1, x2, y2))

        return img.resize((self.size, self.size), self.interpolation)

    def randomize_parameters(self):
        self.scale = self.scales[random.randint(0, len(self.scales) - 1)]
        self.crop_position = self.crop_positions[random.randint(0, len(self.crop_positions) - 1)]




class FiveCrops(object):
    """Crop the given PIL.Image to randomly selected size.
    A crop of size is selected from scales of the original size.
    A position of cropping is randomly selected from 4 corners and 1 center.
    This crop is finally resized to given size.
    Args:
        scales: cropping scales of the original size
        size: size of the smaller edge
        interpolation: Default: PIL.Image.BILINEAR
    """

    def __init__(self, size, mean=[0.0, 0.0, 0.0], std=[1.0, 1.0, 1.0], interpolation=Image.BILINEAR, tenCrops=False):
        self.size = size
        self.interpolation = interpolation
        self.mean = mean
        self.std = std
        self.to_Tensor = ToTensor()
        self.normalize = Normalize(self.mean, self.std)
        self.tenCrops = tenCrops

    def __call__(self, img, inv, flow):
        # print(img.size[0])
        crop_size = self.size

        image_width = img.size[0]
        image_height = img.size[1]
        crop_positions = []
        # center
        center_x = image_width // 2
        center_y = image_height // 2
        box_half = crop_size // 2
        x1 = center_x - box_half
        y1 = center_y - box_half
        x2 = center_x + box_half
        y2 = center_y + box_half
        crop_positions += [[x1, y1, x2, y2]]
    # tl
        x1 = 0
        y1 = 0
        x2 = crop_size
        y2 = crop_size
        crop_positions += [[x1, y1, x2, y2]]
        # tr
        x1 = image_width - crop_size
        y1 = 1
        x2 = image_width
        y2 = crop_size
        crop_positions += [[x1, y1, x2, y2]]
        # bl
        x1 = 1
        y1 = image_height - crop_size
        x2 = crop_size
        y2 = image_height
        crop_positions += [[x1, y1, x2, y2]]
        # br
        x1 = image_width - crop_size
        y1 = image_height - crop_size
        x2 = image_width
        y2 = image_height
        crop_positions += [[x1, y1, x2, y2]]
        cropped_imgs = [img.crop(crop_positions[i]).resize((self.size, self.size), self.interpolation) for i in range(5)]
        # cropped_imgs = [img.resize(self.size, self.size, self.interpolation) for img in cropped_imgs]
        if self.tenCrops is True:
            if inv is True:
                flipped_imgs = [ImageOps.invert(cropped_imgs[i].transpose(Image.FLIP_LEFT_RIGHT)) for i in range(5)]
            else:
                flipped_imgs = [cropped_imgs[i].transpose(Image.FLIP_LEFT_RIGHT) for i in range(5)]
            cropped_imgs += flipped_imgs
                # cropped_imgs.append(img1.transpose(Image.FLIP_LEFT_RIGHT))

        tensor_imgs = [self.to_Tensor(img, inv, flow) for img in cropped_imgs]

        normalized_imgs = [self.normalize(img, inv, flow) for img in tensor_imgs]
        fiveCropImgs = torch.stack(normalized_imgs, 0)
        return fiveCropImgs

    def randomize_parameters(self):
        pass

class TenCrops(object):
    """Crop the given PIL.Image to randomly selected size.
    A crop of size is selected from scales of the original size.
    A position of cropping is randomly selected from 4 corners and 1 center.
    This crop is finally resized to given size.
    Args:
        scales: cropping scales of the original size
        size: size of the smaller edge
        interpolation: Default: PIL.Image.BILINEAR
    """

    def __init__(self, size, mean=[0.0, 0.0, 0.0], std=[1.0, 1.0, 1.0], interpolation=Image.BILINEAR):
        self.size = size
        self.interpolation = interpolation
        self.mean = mean
        self.std = std
        self.fiveCrops = FiveCrops(self.size, self.mean, self.std, self.interpolation, True)

    def __call__(self, img, inv, flow):
        # print(img.size[0])
        return self.fiveCrops(img, inv, flow)

    def randomize_parameters(self):
        pass


class FlippedImagesTest(object):
    """Image and its horizontally flipped versions
    """

    def __init__(self, mean=[0.0, 0.0, 0.0], std=[1.0, 1.0, 1.0]):
        self.mean = mean
        self.std = std
        self.to_Tensor = ToTensor()
        self.normalize = Normalize(self.mean, self.std)

    def __call__(self, img, inv, flow):
        # print(img.size[0])
        img_flipped = img.transpose(Image.FLIP_LEFT_RIGHT)
        if inv is True:
            img_flipped = ImageOps.invert(img_flipped)

        # center

        tensor_img = self.to_Tensor(img, inv, flow)
        tensor_img_flipped = self.to_Tensor(img_flipped, inv, flow)

        normalized_img = self.normalize(tensor_img, inv, flow)
        normalized_img_flipped = self.normalize(tensor_img_flipped, inv, flow)
        horFlippedTest_imgs = [normalized_img, normalized_img_flipped]
        horFlippedTest_imgs = torch.stack(horFlippedTest_imgs, 0)
        return horFlippedTest_imgs

    def randomize_parameters(self):
        pass
    class Binary(object):

    def __init__(self,threshold):
        self.threshold=threshold
    
    def __call__(self, img_tensor):
        img_tensor.map_(img_tensor,lambda x,_ : 1 if x>self.threshold else 0)
        
    def randomize_parameters(self):
        pass
