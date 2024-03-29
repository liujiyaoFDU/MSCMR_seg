import torch
from torch import nn
import torch.nn.functional as F
import numpy as np


try:
    from PIL import ImageEnhance
    from PIL import Image as pil_image
except ImportError:
    pil_image = None
    ImageEnhance = None

def mask_to_onehot(mask, palette):
    """
    Converts a segmentation mask (H, W, C) to (H, W, K) where the last dim is a one
    hot encoding vector, C is usually 1 or 3, and K is the number of class.
    """
    semantic_map = []
    for colour in palette:
        equality = np.equal(mask, colour)
        class_map = np.all(equality, axis=-1)
        semantic_map.append(class_map)
    semantic_map = np.stack(semantic_map, axis=-1).astype(np.float32)
    return semantic_map


def onehot_to_mask(mask, palette):
    """
    Converts a mask (H, W, K) to (H, W, C)
    """
    x = np.argmax(mask, axis=-1)

    colour_codes = np.array(palette)
    x = colour_codes[x.astype(np.uint8)]
    return x


def array_to_img(x, data_format='channels_last', scale=True, dtype='float32'):
    """Converts a 3D Numpy array to a PIL Image instance.

    # Arguments
        x: Input Numpy array.
        data_format: Image data format.
            either "channels_first" or "channels_last".
        scale: Whether to rescale image values
            to be within `[0, 255]`.
        dtype: Dtype to use.

    # Returns
        A PIL Image instance.

    # Raises
        ImportError: if PIL is not available.
        ValueError: if invalid `x` or `data_format` is passed.
    """
    if pil_image is None:
        raise ImportError('Could not import PIL.Image. '
                          'The use of `array_to_img` requires PIL.')
    x = np.asarray(x, dtype=dtype)
    if x.ndim != 3:
        raise ValueError('Expected image array to have rank 3 (single image). '
                         'Got array with shape: %s' % (x.shape,))

    if data_format not in {'channels_first', 'channels_last'}:
        raise ValueError('Invalid data_format: %s' % data_format)

    # Original Numpy array x has format (height, width, channel)
    # or (channel, height, width)
    # but target PIL image has format (width, height, channel)
    if data_format == 'channels_first':
        x = x.transpose(1, 2, 0)
    if scale:
        x = x + max(-np.min(x), 0)
        x_max = np.max(x)
        if x_max != 0:
            x /= x_max
        x *= 255
    if x.shape[2] == 4:
        # RGBA
        return pil_image.fromarray(x.astype('uint8'), 'RGBA')
    elif x.shape[2] == 3:
        # RGB
        return pil_image.fromarray(x.astype('uint8'), 'RGB')
    elif x.shape[2] == 1:
        # grayscale
        return pil_image.fromarray(x[:, :, 0].astype('uint8'), 'L')
    else:
        raise ValueError('Unsupported channel number: %s' % (x.shape[2],))


def semantic_edge_detection(im, palette):
    """
    :param im: shape [H, W, C]
    :param palette:
    :return: [H, W]
    """
    im = torch.from_numpy(im).unsqueeze(0).permute((0, 3, 1, 2)).contiguous()
    Y = np.array([[0, 0, 0], [1, -1, 0], [0, 0, 0]], dtype='float32')
    X = np.array([[0, 1, 0], [0, -1, 0], [0, 0, 0]], dtype='float32')

    kernely = torch.FloatTensor(Y).expand(1, 1, 3, 3)
    kernelx = torch.FloatTensor(X).expand(1, 1, 3, 3)
    weighty = nn.Parameter(data=kernely, requires_grad=False)
    weightx = nn.Parameter(data=kernelx, requires_grad=False)
    edgey = torch.abs(F.conv2d(im, weighty, padding=1))
    edgex = torch.abs(F.conv2d(im, weightx, padding=1))

    edge = torch.where(edgex > 0, edgex, edgey)
    semantic_edge = edge.detach()
    semantic_edge = np.array(semantic_edge.squeeze())
    for i in range(len(palette) - 1):
        semantic_edge[np.logical_and(semantic_edge > palette[i][0], semantic_edge < palette[i+1][0])] = palette[i+1][0]

    # 获取二进制边界
    binary_edge = semantic_edge.copy()
    binary_edge[binary_edge>0] = 255

    return semantic_edge, binary_edge