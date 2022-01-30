import torch
import torch.nn.functional as F
import tex.core.geometry as geo


def iou_loss(output, target, ignore_zero=True):
    """ IoU 输入： [seq_len, 4] """
    if ignore_zero:
        output = output[(target > 0).any(-1)]
        target = target[(target > 0).any(-1)]
    iou = geo.iou(target, output)
    loss = 1 - iou  # -torch.log(iou) inf会导致模型无法拟合
    return torch.mean(loss)


def distance_iou_loss(output, target, ignore_zero=True):
    """ DIoU 输入： [seq_len, 4] """
    if ignore_zero:
        output = output[(target > 0).any(-1)]
        target = target[(target > 0).any(-1)]
    iou = geo.iou(target, output)
    mbr_diag = geo.diag(geo.mbr(target, output))
    dist_center = geo.center_distance(target, output)
    loss = 1 - iou + dist_center / mbr_diag
    return torch.mean(loss)


def complete_iou_loss(output, target, ignore_zero=True):
    """ CIoU 输入： [seq_len, 4] """
    if ignore_zero:
        output = output[(target > 0).any(-1)]
        target = target[(target > 0).any(-1)]
    iou = geo.iou(target, output)
    mbr_diag = geo.diag(geo.mbr(target, output))
    dist_center = geo.center_distance(target, output)
    t_asp = torch.arctan(geo.aspect_ratio(target))
    p_asp = torch.arctan(geo.aspect_ratio(output))
    value = torch.pow(
        t_asp - p_asp, 2) * (4 / (torch.pi * torch.pi))
    alpha = value / ((1 - iou) + value)  # 完全重合时该值为nan
    loss = 1 - iou + dist_center / mbr_diag + alpha * value
    return torch.mean(loss)


def tile_iou_loss(output, target, ignore_zero=True):
    """
    输入： [seq_len, 4] 暂不支持batch_size维度
    在CIoU基础上增加序列损失：
      f = (重叠面积之和 + | 面积之和 - 最小外接矩形面积 |) / 最小外接矩形面积
      Loss = 1 - iou(mbr(a)， mbr(b)) + | f(a) - f(b) |
    """
    if ignore_zero:
        output = output[(target > 0).any(-1)]
        target = target[(target > 0).any(-1)]
    iou = geo.iou(target, output)
    mbr_diag = geo.diag(geo.mbr(target, output))
    dist_center = geo.center_distance(target, output)
    t_asp = torch.arctan(geo.aspect_ratio(target))
    p_asp = torch.arctan(geo.aspect_ratio(output))
    value = torch.pow(
        t_asp - p_asp, 2) * (4 / (torch.pi * torch.pi))
    alpha = value / ((1 - iou) + value)
    loss = 1 - iou + dist_center / mbr_diag + alpha * value
    p_mbr, p_ssi = geo.mbr(output), geo.sum_si(output)
    t_mbr, t_ssi = geo.mbr(target), geo.sum_si(target)
    p_dist = torch.abs(
        1 - torch.sum(geo.area(output)) / geo.area(p_mbr))
    t_dist = torch.abs(
        1 - torch.sum(geo.area(target)) / geo.area(t_mbr))
    p_tile = p_ssi / geo.area(p_mbr) + p_dist
    t_tile = t_ssi / geo.area(t_mbr) + t_dist
    seq_iou = geo.iou(
        p_mbr.unsqueeze(0), t_mbr.unsqueeze(0)).squeeze(0)
    seq_loss = 1 - seq_iou + torch.abs(p_tile - t_tile)
    return torch.mean(loss) + seq_loss


def cls_loss(output, target, pad_idx=0, smoothing=0.01, weight=None):
    return F.cross_entropy(output, target.to(torch.long),
        ignore_index=pad_idx, label_smoothing=smoothing, weight=weight)


def batch_mean(loss_func, outputs, targets, **kwargs):
    # TODO: 循环效率较低 需要优化
    return torch.mean(
        torch.stack(
            [
                loss_func(
                    outputs[batch], targets[batch], **kwargs)
                for batch in range(targets.size(0))
            ]
        )
    )


def structure_loss(outputs, targets,
                   ignore_zero=True, pad_idx=0, smoothing=0.01, weight=None):
    """ 如果输入box为(x,y,w,h)格式 则设置is_transform为True """
    # outputs tuple([batch_size, seq_len, dim], [batch_size, seq_len, 4])
    # targets tuple([batch_size, seq_len], [batch_size, seq_len, 4])
    cls_output, box_output = outputs
    cls_target, box_target = targets
    cls_loss_value = batch_mean(cls_loss, cls_output, cls_target,
        pad_idx=pad_idx, smoothing=smoothing, weight=weight)
    iou_loss_value = batch_mean(
        tile_iou_loss, box_output, box_target, ignore_zero=ignore_zero)
    return cls_loss_value, iou_loss_value


if __name__ == '__main__':
    a = (
        torch.tensor([[[1.4949, 0.7972, -0.3455, -0.4040, 1.2417, 0.4645, 0.1462,
                  1.9950, 1.3542],
                 [-0.0285, -0.2565, -0.0992, 0.0920, 0.8295, 0.3249, 0.1341,
                  -0.4668, -1.3706],
                 [1.2456, -0.5448, -0.5127, -0.3453, 0.6549, -0.1191, -0.4428,
                  -0.4353, -0.4258]]]),
        torch.tensor([[[0.1, 0.1, 0.1, 0.1], [0.1, 0.1, 0.1, 0.1], [0.1, 0.1, 0.1, 0.1]]], dtype=torch.float64)
    )
    print(a[0].argmax(-1))
    b = (
        torch.tensor([[7, 4, 0]]),
        torch.tensor([[[0.1, 0.1, 0.125, 0.2], [0.1, 0.1, 0.125, 0.2], [0.1, 0.1, 0.125, 0.2]]], dtype=torch.float64)
    )

    print(iou_loss(a[1], b[1]))
    print(distance_iou_loss(a[1], b[1]))
    print(complete_iou_loss(a[1], b[1]))
    print(tile_iou_loss(a[1], b[1]))
