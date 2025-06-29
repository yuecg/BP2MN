import logging
from functools import partial
import torch.nn.functional as F
import torch
import torch.nn as nn
from ops.modules import MSDeformAttn
from timm.models.layers import DropPath
import torch.utils.checkpoint as cp

_logger = logging.getLogger(__name__)


def get_reference_points(spatial_shapes, device):
    reference_points_list = []
    for lvl, (H_, W_) in enumerate(spatial_shapes):
        ref_y, ref_x = torch.meshgrid(
            torch.linspace(0.5, H_ - 0.5, H_, dtype=torch.float32, device=device),
            torch.linspace(0.5, W_ - 0.5, W_, dtype=torch.float32, device=device))
        ref_y = ref_y.reshape(-1)[None] / H_
        ref_x = ref_x.reshape(-1)[None] / W_
        ref = torch.stack((ref_x, ref_y), -1)
        reference_points_list.append(ref)
    reference_points = torch.cat(reference_points_list, 1)
    reference_points = reference_points[:, :, None]
    return reference_points


def deform_inputs(x):
    bs, c, h, w = x.shape
    spatial_shapes = torch.as_tensor([(h // 8, w // 8),
                                      (h // 16, w // 16),
                                      (h // 32, w // 32)],
                                     dtype=torch.long, device=x.device)
    level_start_index = torch.cat((spatial_shapes.new_zeros(
        (1,)), spatial_shapes.prod(1).cumsum(0)[:-1]))
    reference_points = get_reference_points([(h // 16, w // 16)], x.device)
    deform_inputs1 = [reference_points, spatial_shapes, level_start_index]
    
    spatial_shapes = torch.as_tensor([(h // 16, w // 16)], dtype=torch.long, device=x.device)
    level_start_index = torch.cat((spatial_shapes.new_zeros(
        (1,)), spatial_shapes.prod(1).cumsum(0)[:-1]))
    reference_points = get_reference_points([(h // 8, w // 8),
                                                   (h // 16, w // 16),
                                                   (h // 32, w // 32)], x.device)
    deform_inputs2 = [reference_points, spatial_shapes, level_start_index]
    
    return deform_inputs1, deform_inputs2


def deform_inputs_only_one(x, h, w):
    # bs, c, h, w = x.shape
    spatial_shapes = torch.as_tensor([(h // 8, w // 8),
                                      (h // 16, w // 16),
                                      (h // 32, w // 32)],
                                     dtype=torch.long, device=x.device)
    level_start_index = torch.cat((spatial_shapes.new_zeros(
        (1,)), spatial_shapes.prod(1).cumsum(0)[:-1]))
    reference_points = get_reference_points([(h // 8, w // 8),
                                      (h // 16, w // 16),
                                      (h // 32, w // 32)], device=x.device)
    deform_inputs = [reference_points, spatial_shapes, level_start_index]
    
    return deform_inputs


class ConvFFN(nn.Module):
    def __init__(self, in_features, hidden_features=None, out_features=None,
                 act_layer=nn.GELU, drop=0.):
        super().__init__()
        out_features = out_features or in_features
        hidden_features = hidden_features or in_features
        self.fc1 = nn.Linear(in_features, hidden_features)
        self.dwconv = DWConv(hidden_features)
        self.act = act_layer()
        self.fc2 = nn.Linear(hidden_features, out_features)
        self.drop = nn.Dropout(drop)

    def forward(self, x, H, W):
        x = self.fc1(x)
        x = self.dwconv(x, H, W)
        x = self.act(x)
        x = self.drop(x)
        x = self.fc2(x)
        x = self.drop(x)
        return x


class M3(nn.Module):
    def __init__(self, in_features, hidden_features=None, out_features=None,
                 act_layer=nn.GELU, drop=0.):
        super().__init__()
        out_features = out_features or in_features
        hidden_features = hidden_features or in_features
        self.fc1 = nn.Linear(in_features, hidden_features)
        self.dwconv = MultiDWConv(hidden_features)
        self.act = act_layer()
        self.fc2 = nn.Linear(hidden_features, out_features)
        self.drop = nn.Dropout(drop)

    def forward(self, x, H, W):
        x = self.fc1(x)
        x = self.dwconv(x, H, W)
        x = self.act(x)
        x = self.drop(x)
        x = self.fc2(x)
        x = self.drop(x)
        return x


class DWConv(nn.Module):
    def __init__(self, dim=768):
        super().__init__()
        self.dwconv = nn.Conv2d(dim, dim, 3, 1, 1, bias=True, groups=dim)

    def forward(self, x, H, W):
        B, N, C = x.shape
        n = N // 21
        x1 = x[:, 0:16 * n, :].transpose(1, 2).view(B, C, H * 2, W * 2).contiguous()
        x2 = x[:, 16 * n:20 * n, :].transpose(1, 2).view(B, C, H, W).contiguous()
        x3 = x[:, 20 * n:, :].transpose(1, 2).view(B, C, H // 2, W // 2).contiguous()
        x1 = self.dwconv(x1).flatten(2).transpose(1, 2)
        x2 = self.dwconv(x2).flatten(2).transpose(1, 2)
        x3 = self.dwconv(x3).flatten(2).transpose(1, 2)
        x = torch.cat([x1, x2, x3], dim=1)
        return x
    

class MultiDWConv(nn.Module):
    def __init__(self, dim=768):
        super().__init__()
        dim_quarter = dim // 4  
        
        
        self.dwconv1_3x3 = nn.Conv2d(dim_quarter, dim_quarter, 3, 1, 1, bias=True, groups=dim_quarter)
        self.dwconv1_5x5 = nn.Conv2d(dim_quarter, dim_quarter, 5, 1, 2, bias=True, groups=dim_quarter)
        self.dwconv1_7x7 = nn.Conv2d(dim_quarter, dim_quarter, 7, 1, 3, bias=True, groups=dim_quarter)
        self.dwconv1_9x9 = nn.Conv2d(dim_quarter, dim_quarter, 9, 1, 4, bias=True, groups=dim_quarter)
        
        
        self.dwconv2_3x3 = nn.Conv2d(dim_quarter, dim_quarter, 3, 1, 1, bias=True, groups=dim_quarter)
        self.dwconv2_5x5 = nn.Conv2d(dim_quarter, dim_quarter, 5, 1, 2, bias=True, groups=dim_quarter)
        self.dwconv2_7x7 = nn.Conv2d(dim_quarter, dim_quarter, 7, 1, 3, bias=True, groups=dim_quarter)
        self.dwconv2_9x9 = nn.Conv2d(dim_quarter, dim_quarter, 9, 1, 4, bias=True, groups=dim_quarter)
        
        
        self.dwconv3_3x3 = nn.Conv2d(dim_quarter, dim_quarter, 3, 1, 1, bias=True, groups=dim_quarter)
        self.dwconv3_5x5 = nn.Conv2d(dim_quarter, dim_quarter, 5, 1, 2, bias=True, groups=dim_quarter)
        self.dwconv3_7x7 = nn.Conv2d(dim_quarter, dim_quarter, 7, 1, 3, bias=True, groups=dim_quarter)
        self.dwconv3_9x9 = nn.Conv2d(dim_quarter, dim_quarter, 9, 1, 4, bias=True, groups=dim_quarter)
        
        
        self.act = nn.GELU()  
        self.bn1 = nn.BatchNorm2d(dim)  
        self.bn2 = nn.BatchNorm2d(dim)  
        self.bn3 = nn.BatchNorm2d(dim)  

    def forward(self, x, H, W):
        B, N, C = x.shape
        n = N // 21
        
        
        x1 = x[:, 0:16*n, :].transpose(1, 2).view(B, C, H*2, W*2).contiguous()  
        x2 = x[:, 16*n:20*n, :].transpose(1, 2).view(B, C, H, W).contiguous()    
        x3 = x[:, 20*n:, :].transpose(1, 2).view(B, C, H//2, W//2).contiguous() 
        
       
        x11 = x1[:, 0*C//4:1*C//4, :, :]
        x12 = x1[:, 1*C//4:2*C//4, :, :]
        x13 = x1[:, 2*C//4:3*C//4, :, :]
        x14 = x1[:, 3*C//4:, :, :]
        
        x11 = self.dwconv1_3x3(x11)  # 3x3
        x12 = self.dwconv1_5x5(x12)  # 5x5
        x13 = self.dwconv1_7x7(x13)  # 7x7
        x14 = self.dwconv1_9x9(x14)  # 9x9
        
        x1 = torch.cat([x11, x12, x13, x14], dim=1)
        x1 = self.act(self.bn1(x1)).flatten(2).transpose(1, 2)
        
        
        x21 = x2[:, 0*C//4:1*C//4, :, :]
        x22 = x2[:, 1*C//4:2*C//4, :, :]
        x23 = x2[:, 2*C//4:3*C//4, :, :]
        x24 = x2[:, 3*C//4:, :, :]
        
        x21 = self.dwconv2_3x3(x21)
        x22 = self.dwconv2_5x5(x22)
        x23 = self.dwconv2_7x7(x23)
        x24 = self.dwconv2_9x9(x24)
        
        x2 = torch.cat([x21, x22, x23, x24], dim=1)
        x2 = self.act(self.bn2(x2)).flatten(2).transpose(1, 2)
        
        
        x31 = x3[:, 0*C//4:1*C//4, :, :]
        x32 = x3[:, 1*C//4:2*C//4, :, :]
        x33 = x3[:, 2*C//4:3*C//4, :, :]
        x34 = x3[:, 3*C//4:, :, :]
        
        x31 = self.dwconv3_3x3(x31)
        x32 = self.dwconv3_5x5(x32)
        x33 = self.dwconv3_7x7(x33)
        x34 = self.dwconv3_9x9(x34)
        
        x3 = torch.cat([x31, x32, x33, x34], dim=1)
        x3 = self.act(self.bn3(x3)).flatten(2).transpose(1, 2)
        
    
        x = torch.cat([x1, x2, x3], dim=1)
        return x

class MultiscaleExtractor(nn.Module):
    def __init__(self, dim, num_heads=6, n_points=4, n_levels=1, deform_ratio=1.0,
                 with_cffn=True, cffn_ratio=0.25, drop=0., drop_path=0.,
                 norm_layer=partial(nn.LayerNorm, eps=1e-6), with_cp=False):
        super().__init__()
        self.query_norm = norm_layer(dim)
        self.feat_norm = norm_layer(dim)
        self.attn = MSDeformAttn(d_model=dim, n_levels=n_levels, n_heads=num_heads,
                                 n_points=n_points, ratio=deform_ratio)
        self.with_cffn = with_cffn
        self.with_cp = with_cp
        if with_cffn:
            self.ffn = ConvFFN(in_features=dim, hidden_features=int(dim * cffn_ratio), drop=drop)
            self.ffn_norm = norm_layer(dim)
            self.drop_path = DropPath(drop_path) if drop_path > 0. else nn.Identity()

    
    def forward(self, query, reference_points, feat, spatial_shapes, level_start_index, H, W):
        
        def _inner_forward(query, feat):
            
            attn = self.attn(self.query_norm(query), reference_points,
                             self.feat_norm(feat), spatial_shapes,
                             level_start_index, None)
            query = query + attn
            
            if self.with_cffn:
                query = query + self.drop_path(self.ffn(self.ffn_norm(query), H, W))

            return query
        
        if self.with_cp and query.requires_grad:
            query = cp.checkpoint(_inner_forward, query, feat)
        else:
            query = _inner_forward(query, feat)
        
        return query


class LGTM_toC(nn.Module):
    def __init__(self, dim, num_heads=6, n_points=4, n_levels=1, deform_ratio=1.0,
                 with_cffn=True, cffn_ratio=0.25, drop=0., drop_path=0.,
                 norm_layer=partial(nn.LayerNorm, eps=1e-6), with_cp=False,
                 cnn_feature_interaction=True):
        super().__init__()
        self.query_norm = norm_layer(dim)
        self.feat_norm = norm_layer(dim)
        self.with_cffn = with_cffn
        self.with_cp = with_cp
        # if with_cffn:
        #     self.ffn = ConvFFN(in_features=dim, hidden_features=int(dim * cffn_ratio), drop=drop)
        #     self.ffn_norm = norm_layer(dim)
        #     self.drop_path = DropPath(drop_path) if drop_path > 0. else nn.Identity()
        
        self.cnn_feature_interaction = cnn_feature_interaction
        if cnn_feature_interaction:
            self.cfinter = MultiscaleExtractor(dim=dim, n_levels=3, num_heads=num_heads,
                                n_points=n_points, norm_layer=norm_layer, 
                                deform_ratio=deform_ratio, with_cffn=with_cffn,
                                cffn_ratio=cffn_ratio, drop=drop, drop_path=drop_path, 
                                with_cp=with_cp)
    
    def forward(self, query, reference_points, feat, spatial_shapes, level_start_index, H, W):
        
        def _inner_forward(query, feat, H, W):
            B, N, C = query.shape
            n = N // 21
            x1 = query[:, 0:16 * n, :].contiguous()
            x2 = query[:, 16 * n:20 * n, :].contiguous()
            x3 = query[:, 20 * n:, :].contiguous()
            x2 = x2 + feat
            query = torch.cat([x1, x2, x3], dim=1)

            # if self.with_cffn:
            #     query = query + self.drop_path(self.ffn(self.ffn_norm(query), H, W)) 

            if self.cnn_feature_interaction:               
                deform_input = deform_inputs_only_one(query, H*16, W*16)
                query = self.cfinter(query=self.query_norm(query), reference_points=deform_input[0],
                          feat=self.feat_norm(query), spatial_shapes=deform_input[1],
                          level_start_index=deform_input[2],
                          H=H, W=W)               
            
            return query
        
        if self.with_cp and query.requires_grad:
            query = cp.checkpoint(_inner_forward, query, feat, H, W)
        else:
            query = _inner_forward(query, feat, H, W)
        
        return query

class Extractor_LGTM(nn.Module):
    def __init__(self, dim, num_heads=6, n_points=4, n_levels=1, deform_ratio=1.0,
                 with_cffn=True, cffn_ratio=0.25, drop=0., drop_path=0.,
                 norm_layer=partial(nn.LayerNorm, eps=1e-6), with_cp=False,
                 cnn_feature_interaction=True):
        super().__init__()
        self.query_norm = norm_layer(dim)
        self.feat_norm = norm_layer(dim)
        self.with_cffn = with_cffn
        self.with_cp = with_cp
        if with_cffn:
            self.ffn = ConvFFN(in_features=dim, hidden_features=int(dim * cffn_ratio), drop=drop)
            self.ffn_norm = norm_layer(dim)
            self.drop_path = DropPath(drop_path) if drop_path > 0. else nn.Identity()
        
        self.cnn_feature_interaction = cnn_feature_interaction
        if cnn_feature_interaction:
            self.cfinter = MultiscaleExtractor(dim=dim, n_levels=3, num_heads=num_heads,
                                n_points=n_points, norm_layer=norm_layer, 
                                deform_ratio=deform_ratio, with_cffn=with_cffn,
                                cffn_ratio=cffn_ratio, drop=drop, drop_path=drop_path, 
                                with_cp=with_cp)
    
    def forward(self, query, reference_points, feat, spatial_shapes, level_start_index, H, W):
        
        def _inner_forward(query, feat, H, W):
            B, N, C = query.shape
            n = N // 21
            x1 = query[:, 0:16 * n, :].contiguous()
            x2 = query[:, 16 * n:20 * n, :].contiguous()
            x3 = query[:, 20 * n:, :].contiguous()
            x2 = x2 + feat
            query = torch.cat([x1, x2, x3], dim=1)

            if self.with_cffn:
                query = query + self.drop_path(self.ffn(self.ffn_norm(query), H, W)) 

            if self.cnn_feature_interaction:               
                deform_input = deform_inputs_only_one(query, H*16, W*16)
                query = self.cfinter(query=self.query_norm(query), reference_points=deform_input[0],
                          feat=self.feat_norm(query), spatial_shapes=deform_input[1],
                          level_start_index=deform_input[2],
                          H=H, W=W)               
            
            return query
        
        if self.with_cp and query.requires_grad:
            query = cp.checkpoint(_inner_forward, query, feat, H, W)
        else:
            query = _inner_forward(query, feat, H, W)
        
        return query



class LGTM_toV(nn.Module):
    def __init__(self, dim, num_heads=6, n_points=4, n_levels=1, deform_ratio=1.0,
                 norm_layer=partial(nn.LayerNorm, eps=1e-6), init_values=0., with_cp=False, drop=0., drop_path=0., cffn_ratio=0.25):
        super().__init__()
        self.with_cp = with_cp
        self.query_norm = norm_layer(dim)
        self.feat_norm = norm_layer(dim)
        self.attn = MSDeformAttn(d_model=dim, n_levels=n_levels, n_heads=num_heads,
                                 n_points=n_points, ratio=deform_ratio)
        self.gamma = nn.Parameter(init_values * torch.ones((dim)), requires_grad=True)

        self.ffn = ConvFFN(in_features=dim, hidden_features=int(dim * cffn_ratio), drop=drop)
        self.ffn_norm = norm_layer(dim)
        self.drop_path = DropPath(drop_path) if drop_path > 0. else nn.Identity()
       
    
    def forward(self, query, reference_points, feat, spatial_shapes, level_start_index, H, W):
        
        def _inner_forward(query, feat, H, W):
            B, N, C = feat.shape
            c1 = self.attn(self.query_norm(feat), reference_points,
                             self.feat_norm(feat), spatial_shapes,
                             level_start_index, None)

            c1 = c1 + self.drop_path(self.ffn(self.ffn_norm(c1), H, W)) 

            c_select1, c_select2, c_select3 = c1[:,:H*W*4, :], c1[:, H*W*4:H*W*4+H*W, :], c1[:, H*W*4+H*W:, :]
            c_select1 = F.interpolate(c_select1.permute(0,2,1).reshape(B, C, H*2, W*2), scale_factor=0.5, mode='bilinear', align_corners=False).flatten(2).permute(0,2,1)
            c_select3 = F.interpolate(c_select3.permute(0,2,1).reshape(B, C, H//2, W//2), scale_factor=2, mode='bilinear', align_corners=False).flatten(2).permute(0,2,1)
            # x = x + c_select1 + c_select2 + c_select3

            return query + self.gamma * (c_select1 + c_select2 + c_select3)
        
        if self.with_cp and query.requires_grad:
            query = cp.checkpoint(_inner_forward, query, feat, H, W)
        else:
            query = _inner_forward(query, feat, H, W)
        
        return query


class LGTMBlock(nn.Module):
    def __init__(self, dim, num_heads=6, n_points=4, norm_layer=partial(nn.LayerNorm, eps=1e-6),
                 drop=0., drop_path=0., with_cffn=True, cffn_ratio=0.25, init_values=0.,
                 deform_ratio=1.0, extra_LGTM=False, with_cp=False,
                 use_LGTM_toV=True,
                 use_LGTM_toC=True,
                 dim_ratio=6.0,
                 cnn_feature_interaction=False):
        super().__init__()

        if use_LGTM_toV:
            self.lgtm_tov = LGTM_toV(dim=dim, n_levels=3, num_heads=num_heads, init_values=init_values,
                                 n_points=n_points, norm_layer=norm_layer, deform_ratio=deform_ratio,
                                 with_cp=with_cp, drop=drop, drop_path=drop_path, cffn_ratio=cffn_ratio)
        if use_LGTM_toC:
            self.lgtm_toc = LGTM_toC(dim=dim, n_levels=1, num_heads=num_heads, n_points=n_points,
                                   norm_layer=norm_layer, deform_ratio=deform_ratio, with_cffn=with_cffn,
                                   cffn_ratio=cffn_ratio, drop=drop, drop_path=drop_path, with_cp=with_cp,
                                   cnn_feature_interaction=cnn_feature_interaction)
        
        if extra_LGTM:
            self.extra_LGTMs = nn.Sequential(*[
                Extractor_LGTM(dim=dim, n_levels=1, num_heads=num_heads, n_points=n_points,
                                   norm_layer=norm_layer, deform_ratio=deform_ratio, with_cffn=with_cffn,
                                   cffn_ratio=cffn_ratio, drop=drop, drop_path=drop_path, with_cp=with_cp,
                                   cnn_feature_interaction=cnn_feature_interaction)
                for _ in range(4)
            ])

        else:
            self.extra_LGTMs = None
        
        self.use_LGTM_toV = use_LGTM_toV
        self.use_LGTM_toC = use_LGTM_toC

        self.mrfp = MRFP(dim, hidden_features=int(dim * dim_ratio))

    
    def forward(self, x, c, blocks, deform_inputs1, deform_inputs2, H, W):
        B, N, C = x.shape
        deform_inputs = deform_inputs_only_one(x, H*16, W*16)
        if self.use_LGTM_toV:
            c = self.mrfp(c, H, W)
            c_select1, c_select2, c_select3 = c[:,:H*W*4, :], c[:, H*W*4:H*W*4+H*W, :], c[:, H*W*4+H*W:, :]
            c = torch.cat([c_select1, c_select2 + x, c_select3], dim=1)

            x = self.lgtm_tov(query=x, reference_points=deform_inputs[0],
                          feat=c, spatial_shapes=deform_inputs[1],
                          level_start_index=deform_inputs[2], H=H, W=W)

        for idx, blk in enumerate(blocks):
            x = blk(x, H, W)

        if self.use_LGTM_toC:
            c = self.lgtm_toc(query=c, reference_points=deform_inputs2[0],
                           feat=x, spatial_shapes=deform_inputs2[1],
                           level_start_index=deform_inputs2[2], H=H, W=W)
                           
        if self.extra_LGTMs is not None:
            for lgtm in self.extra_LGTMs:
                c = lgtm(query=c, reference_points=deform_inputs2[0],
                              feat=x, spatial_shapes=deform_inputs2[1],
                              level_start_index=deform_inputs2[2], H=H, W=W)
        return x, c


class CNN(nn.Module):
    def __init__(self, inplanes=64, embed_dim=384):
        super().__init__()

        self.stem = nn.Sequential(*[
            nn.Conv2d(3, inplanes, kernel_size=3, stride=2, padding=1, bias=False),
            nn.SyncBatchNorm(inplanes),
            nn.ReLU(inplace=True),
            nn.Conv2d(inplanes, inplanes, kernel_size=3, stride=1, padding=1, bias=False),
            nn.SyncBatchNorm(inplanes),
            nn.ReLU(inplace=True),
            nn.Conv2d(inplanes, inplanes, kernel_size=3, stride=1, padding=1, bias=False),
            nn.SyncBatchNorm(inplanes),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(kernel_size=3, stride=2, padding=1)
        ])
        self.conv2 = nn.Sequential(*[
            nn.Conv2d(inplanes, 2 * inplanes, kernel_size=3, stride=2, padding=1, bias=False),
            nn.SyncBatchNorm(2 * inplanes),
            nn.ReLU(inplace=True)
        ])
        self.conv3 = nn.Sequential(*[
            nn.Conv2d(2 * inplanes, 4 * inplanes, kernel_size=3, stride=2, padding=1, bias=False),
            nn.SyncBatchNorm(4 * inplanes),
            nn.ReLU(inplace=True)
        ])
        self.conv4 = nn.Sequential(*[
            nn.Conv2d(4 * inplanes, 4 * inplanes, kernel_size=3, stride=2, padding=1, bias=False),
            nn.SyncBatchNorm(4 * inplanes),
            nn.ReLU(inplace=True)
        ])
        self.fc1 = nn.Conv2d(inplanes, embed_dim, kernel_size=1, stride=1, padding=0, bias=True)
        self.fc2 = nn.Conv2d(2 * inplanes, embed_dim, kernel_size=1, stride=1, padding=0, bias=True)
        self.fc3 = nn.Conv2d(4 * inplanes, embed_dim, kernel_size=1, stride=1, padding=0, bias=True)
        self.fc4 = nn.Conv2d(4 * inplanes, embed_dim, kernel_size=1, stride=1, padding=0, bias=True)

    def forward(self, x):
        c1 = self.stem(x)
        c2 = self.conv2(c1)
        c3 = self.conv3(c2)
        c4 = self.conv4(c3)
        c1 = self.fc1(c1)
        c2 = self.fc2(c2)
        c3 = self.fc3(c3)
        c4 = self.fc4(c4)

        bs, dim, _, _ = c1.shape
        # c1 = c1.view(bs, dim, -1).transpose(1, 2)  # 4s
        c2 = c2.view(bs, dim, -1).transpose(1, 2)  # 8s
        c3 = c3.view(bs, dim, -1).transpose(1, 2)  # 16s
        c4 = c4.view(bs, dim, -1).transpose(1, 2)  # 32s

        return c1, c2, c3, c4
