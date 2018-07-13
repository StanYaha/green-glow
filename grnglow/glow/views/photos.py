# -*- encoding: utf-8 -*-
'''
Created on 2012-3-23

@author: Neil
'''
from django.shortcuts import render_to_response
from django.http import HttpResponseRedirect, HttpResponse
from grnglow.glow.models.album import Album
from grnglow.glow.models.photo import Photo
from grnglow.glow.models.user import User
from grnglow.glow.models.like import Like
from grnglow import settings
from grnglow.glow.views import error_404
from grnglow.glow.models.comment import Comment
from django.views.decorators.csrf import csrf_protect, csrf_exempt
import string, datetime, json
import sys
from django.template.loader import get_template
from django.template.context import Context

UPLOAD_PHOTOS_SESSION_KEY = 'upload_photos'  # 用于存放上传的照片片在数据库中的id元组
UPLOAD_ALBUM_SESSION_KEY = 'upload_album'  # 用于存放用户上传到的相册ID
UPLOAD_STEP1_SESSION_KEY = 'upload_step1'  # 用于判断上传时，是否通过了第一步
UPLOAD_STEP2_SESSION_KEY = 'upload_step2'  # 用于判断上传时，是否通过了第二步


# 只允许上传jpg文件，在前端已做校验
@csrf_protect
def upload(request):
    # 只有登录用户才可以上传
    if not request.user.is_authenticated():
        return error_404(request)

    if request.method == 'POST':
        photo_id_list = []
        for i in request.FILES:
            photo = Photo()
            photo.save_photo_brief(request.user, request.FILES[i], request.POST['album_id'])
            photo_id_list.append(photo.id)

        album_id = string.atoi(request.POST['album_id'])
        try:
            album = Album.objects.get(owner=request.user, id=album_id)
        except:
            pass
        else:
            album.photo_count += len(photo_id_list)  # 增加相册照片数
            request.user.photo_count += len(photo_id_list)  # 增加用户照片数
            album.last_post = datetime.datetime.now()
            album.save()
            request.user.save()

        request.session[UPLOAD_PHOTOS_SESSION_KEY] = tuple(photo_id_list)  # 转换成元组
        request.session[UPLOAD_STEP1_SESSION_KEY] = True  # 通过第一步
        request.session[UPLOAD_ALBUM_SESSION_KEY] = request.POST.get('album_id')
        return HttpResponseRedirect('complete/')  # 跳转到照片信息编辑页
    else:
        album_list = Album.objects.filter(owner=request.user)  # 获取该用户的所有相册
        return render_to_response('photos/upload.html', {'request': request, 'album_list': album_list})


@csrf_protect
def upload_complete(request):
    # 只有登录用户，已通过第一步的前提下，才可以操作，
    if (not request.user.is_authenticated()) or \
            (UPLOAD_PHOTOS_SESSION_KEY not in request.session) or \
            (UPLOAD_STEP1_SESSION_KEY not in request.session) or \
            (not request.session[UPLOAD_STEP1_SESSION_KEY]):
        return error_404(request)

    if request.method == 'POST':
        photo_id_list = request.session[UPLOAD_PHOTOS_SESSION_KEY]
        for p_id in photo_id_list:
            try:
                photo = Photo.objects.get(id=p_id)
            except:
                pass
            else:
                title = (request.POST.get(str(p_id) + '_title', '')).strip()  # 去掉两端的空格
                caption = (request.POST.get(str(p_id) + '_caption', '')).strip()  # 去掉两端的空格
                tags = (request.POST.get(str(p_id) + '_tags', '')).strip()
                tags = tags.replace(u'，', ',')  # 把中文的逗号'，'替换成英文的','
                tag_list = tags.split(',')
                photo.save_photo_description(request.user, title, caption, tag_list)

        request.session[UPLOAD_STEP1_SESSION_KEY] = False
        request.session[UPLOAD_STEP2_SESSION_KEY] = True  # 通过第二步
        return HttpResponseRedirect('done/')  # 跳转到照片上传完成页
    else:
        photo_id_list = request.session[UPLOAD_PHOTOS_SESSION_KEY]
        photo_list = []
        for p_id in photo_id_list:
            photo = Photo.objects.get(id=p_id)
            photo.input_title_name = str(photo.id) + '_title'
            photo.input_caption_name = str(photo.id) + '_caption'
            photo.input_tags_name = str(photo.id) + '_tags'
            photo_list.append(photo)

        return render_to_response('photos/upload_complete.html', {'request': request, 'photo_list': photo_list})


def upload_done(request):
    # 只有登录用户才可以操作
    if not request.user.is_authenticated():
        return error_404(request)

    if UPLOAD_STEP2_SESSION_KEY in request.session and request.session[UPLOAD_STEP2_SESSION_KEY]:  # 通过第二步
        # request.session[UPLOAD_STEP1_SESSION_KEY] = False
        request.session[UPLOAD_STEP2_SESSION_KEY] = False
        return render_to_response('photos/upload_done.html', {'request': request})
    else:
        return error_404(request)


@csrf_protect
def photo(request, user_id, photo_id):
    try:
        people = User.objects.get(id=user_id)
        photo = Photo.objects.get(owner=people, id=photo_id)

    except User.DoesNotExist, Photo.DoesNotExist:
        return error_404(request)

    try:
        comment_list = Comment.objects.filter(photo_id=photo.id, photo_owner=people,
                                              deleted_by_photo_owner=False).order_by('date_posted')
    except:
        comment_list = []

    is_myPage = False  # 用来标记该页面是不是登录用户的个人页面
    if request.user.is_authenticated():
        if str(request.user.id) == user_id:  # 注意user_id是unicode字符串，比较时要先转成字符串
            is_myPage = True  # 自己的页面可以删除评论，删除照片
        else:
            is_myPage = False

            try:
                Like.objects.get(photo_id=photo.id, photo_owner=people, user=request.user)
            except Like.DoesNotExist:
                photo.i_like = False
            else:
                photo.i_like = True

    # 该照片在该相册中是第几张
    photo.album.current_p = photo.album.photo_count - Photo.objects.filter(owner=photo.owner, album=photo.album,
                                                                           id__gt=photo.id).count()  # id__gt表示id大于

    return render_to_response('photos/photo.html', {'request': request, 'people': people,
                                                    'photo': photo, 'is_myPage': is_myPage, 'album': photo.album,
                                                    'comment_list': comment_list})


# 下一张照片
def next_photo(request, user_id, photo_id):
    try:
        people = User.objects.get(id=user_id)
        photo = Photo.objects.get(owner=people, id=photo_id)
        try:
            # id__gt表示id大于
            next_photo = Photo.objects.filter(id__gt=photo_id, owner=photo.owner, album=photo.album).order_by('id')[0]
            next_photo_id = next_photo.id
        except:  # 不存在上一张照片，就用当前这张
            next_photo_id = photo_id
    except User.DoesNotExist, Photo.DoesNotExist:
        return error_404(request)

    # 跳转到该照片的页面
    return HttpResponseRedirect(settings.HOME_PAGE_URL + 'photos/'
                                + str(user_id) + '/' + str(next_photo_id) + '/')


# 上一张照片
def prev_photo(request, user_id, photo_id):
    try:
        people = User.objects.get(id=user_id)
        photo = Photo.objects.get(owner=people, id=photo_id)
        try:
            # id__lt表示id小于
            prev_photo = Photo.objects.filter(id__lt=photo_id, owner=photo.owner, album=photo.album).order_by('-id')[0]
            prev_photo_id = prev_photo.id
        except:  # 不存在上一张照片，就用当前这张
            prev_photo_id = photo_id
    except User.DoesNotExist, Photo.DoesNotExist:
        return error_404(request)

    return HttpResponseRedirect(settings.HOME_PAGE_URL
                                + 'photos/' + str(user_id) + '/' + str(prev_photo_id) + '/')  # 跳转到该照片的页面


# 编辑照片的信息
@csrf_protect
def edit(request, user_id, photo_id):
    # 只有登录用户，且是自己的照片，才可以操作，
    if not request.user.is_authenticated() or str(request.user.id) != user_id:
        return error_404(request)

    try:
        photo = Photo.objects.get(owner=request.user, id=photo_id)
    except:
        return error_404(request)

    if request.method == 'POST':
        if request.POST.get('update') == u'更新':
            title = (request.POST.get('title', '')).strip()  # 去掉两端的空格
            caption = (request.POST.get('caption', '')).strip()  # 去掉两端的空格
            tags = request.POST.get('tags', '').strip()  # 去掉两端的空格
            tags = tags.replace(u'，', ',')  # 把中文的逗号'，'替换成英文的','
            tag_list = tags.split(',')
            photo.update_photo_info(title, caption, tag_list)
        elif request.POST.get('cancel') == u'撤销':
            pass

        return HttpResponseRedirect(settings.HOME_PAGE_URL
                                    + 'photos/' + str(user_id) + '/' + str(photo_id) + '/')  # 跳转到该照片的页面

    else:
        tag_list = []
        for tag in photo.tags.all():
            tag_list.append(tag.name)
        photo.tagStr = u'，'.join(tag_list)

        return render_to_response('photos/edit.html', {'request': request, 'photo': photo})


@csrf_exempt  # 若没有csrf处理，服务器会返回403 forbidden错误
def ajax_deletePhoto(request, user_id, photo_id):
    if not request.is_ajax() or (request.method != 'POST'):
        return HttpResponse(json.dumps({"status": 'error0'}))

    # 只有登录用户，且是自己的照片，才可以操作，
    if not request.user.is_authenticated() or str(request.user.id) != user_id:
        return HttpResponse(json.dumps({"status": 'error1'}))

    try:
        photo = Photo.objects.get(id=photo_id)
        photo.clearPhoto()
        photo.delete()
        photo.deletePhotoFiles()  # 删除照片文件
    except:
        return HttpResponse(json.dumps({"status": str(sys.exc_info()[0]) + str(sys.exc_info()[1])}))

    return HttpResponse(json.dumps({"status": 'success'}))


@csrf_exempt  # 若没有csrf处理，服务器会返回403 forbidden错误
def ajax_markLike(request, user_id, photo_id):
    if not request.is_ajax() or (request.method != 'POST'):
        return HttpResponse(json.dumps({"status": 'error0'}))

    # 只有登录用户，且不是自己的照片，才可以操作，
    if not request.user.is_authenticated() or str(request.user.id) == user_id:
        return HttpResponse(json.dumps({"status": 'error1'}))

    try:
        people = User.objects.get(id=user_id)
        like = Like(photo_id=photo_id, photo_owner=people, user=request.user)
        if like.isExist():  # 判断该喜欢记录是否已存在，避免重复喜欢
            return HttpResponse(json.dumps({"status": 'success'}))
        like.calPhotoScore(True)  # 添加喜欢后重新计算照片得分
        like.save()

    except:
        return HttpResponse(json.dumps({"status": str(sys.exc_info()[0]) + str(sys.exc_info()[1])}))

    return HttpResponse(json.dumps({"status": 'success'}))


@csrf_exempt  # 若没有csrf处理，服务器会返回403 forbidden错误
def ajax_cancelLike(request, user_id, photo_id):
    if not request.is_ajax() or (request.method != 'POST'):
        return HttpResponse(json.dumps({"status": 'error0'}))

    # 只有登录用户，且不是自己的照片，才可以操作，
    if not request.user.is_authenticated() or str(request.user.id) == user_id:
        return HttpResponse(json.dumps({"status": 'error1'}))

    try:
        people = User.objects.get(id=user_id)  # people是照片拥有者

        like = Like.objects.get(photo_id=photo_id, photo_owner=people, user=request.user)
        like.calPhotoScore(False)  # 取消喜欢后重新计算照片得分
        like.delete()
    except:
        return HttpResponse(json.dumps({"status": str(sys.exc_info()[0]) + str(sys.exc_info()[1])}))

    return HttpResponse(json.dumps({"status": 'success'}))


@csrf_exempt  # 若没有csrf处理，服务器会返回403 forbidden错误
def ajax_addComment(request, user_id, photo_id):
    if not request.is_ajax() or (request.method != 'POST'):
        return HttpResponse(json.dumps({"status": 'error0'}))

    # 只有登录用户，才可以操作，
    if not request.user.is_authenticated():
        return HttpResponse(json.dumps({"status": 'error1'}))

    try:
        people = User.objects.get(id=user_id)  # people是照片拥有者
        content = (request.POST.get('content')).strip()
        if content != '':
            comment = Comment(photo_id=photo_id, photo_owner=people, author=request.user, content=content)
            comment.save()  # 保存评论

            t = get_template('photos/comment_item.html')
            html = t.render(Context({'comment': comment, 'request': request}))
        else:
            html = ''
        return HttpResponse(json.dumps({'status': 'success', 'html': html}))
    except:
        return HttpResponse(json.dumps({'status': str(sys.exc_info()[0]) + str(sys.exc_info()[1])}))


@csrf_exempt  # 若没有csrf处理，服务器会返回403 forbidden错误
def ajax_deleteComment(request):
    if not request.is_ajax() or (request.method != 'POST'):
        return HttpResponse(json.dumps({"status": 'error0'}))

    # 只有登录用户，才可以操作，
    if not request.user.is_authenticated():
        return HttpResponse(json.dumps({"status": 'no authority'}))

    user_id = request.POST.get('user_id')
    # photo_id = request.POST.get('photo_id')
    author_id = request.POST.get('author_id')
    comment_id = request.POST.get('comment_id')  # 这里的comment_id是照片所在站点的评论的id
    if author_id != str(request.user.id) and str(request.user.id) != user_id:  # 没有删除权限
        return HttpResponse(json.dumps({"status": 'xx' + user_id + 'no authority to delete this comment'}))

    try:
        # people = User.objects.get(id=user_id)  # people是照片拥有者
        # author = User.objects.get(id=author_id)

        if str(request.user.id) == author_id:  # 如果执行删除操作的是评论者，则删除评论
            c = Comment.objects.get(id=comment_id)
            c.delete()  # 删除评论
        else:  # 如果执行删除操作的是照片所有者，则不删除评论，但标记评论被照片所有者删除，即评论在照片评论列表不可见
            c = Comment.objects.get(id=comment_id)
            # if author.city != people.city:  # 评论用户和照片所有者不在同一个站点，存在评论副本
            #     rc = Comment.objects.get(id=c.master_id)
            #     rc.deleted_by_photo_owner = True
            #     rc.save()
            c.deleted_by_photo_owner = True
            c.save()  # 删除评论
    except Comment.DoesNotExist:  # 评论不存在，或已删除，返回成功
        return HttpResponse(json.dumps({'status': 'success'}))
    except:
        return HttpResponse(json.dumps({'status': str(sys.exc_info()[0]) + str(sys.exc_info()[1])}))

    return HttpResponse(json.dumps({'status': 'success'}))


# @csrf_exempt  # 若没有csrf处理，服务器会返回403 forbidden错误
# def ajax_deleteComment2(request, user_id, photo_id):
#     if not request.is_ajax() or (request.method != 'POST'):
#         return HttpResponse(json.dumps({"status": 'error0'}))
#
#     # 只有登录用户，才可以操作，
#     if not request.user.is_authenticated():
#         return HttpResponse(json.dumps({"status": 'error1'}))
#
#     author_id = request.POST.get('author_id')
#     comment_id = request.POST.get('comment_id')  # 这里的comment_id是照片所在站点的评论的id
#     if author_id != str(request.user.id) and str(request.user.id) != user_id:  # 没有删除权限
#         return HttpResponse(json.dumps({"status": 'error2'}))
#
#     try:
#         if str(request.user.id) == author_id:  # 如果执行删除操作的是评论者，则删除评论
#             c = Comment.objects.get(id=comment_id)
#             c.delete()  # 删除评论
#         else:  # 如果执行删除操作的是照片所有者，则不删除评论，但标记评论被照片所有者删除，即评论在照片评论列表不可见
#             c = Comment.objects.get(id=comment_id)
#             c.deleted_by_photo_owner = True
#             c.save()  # 删除评论
#     except Comment.DoesNotExist:  # 评论不存在，或已删除，返回成功
#         return HttpResponse(json.dumps({'status': 'success'}))
#     except:
#         return HttpResponse(json.dumps({'status': str(sys.exc_info()[0]) + str(sys.exc_info()[1])}))
#
#     return HttpResponse(json.dumps({'status': 'success'}))
