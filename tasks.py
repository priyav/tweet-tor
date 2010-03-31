import os
from pyres import *
import PIL
from PIL import Image
from settings import *
import copy
import tornado.database

database = tornado.database.Connection(host=MYSQL_HOST, database=MYSQL_DATABASE, user=MYSQL_USER, password=MYSQL_PASSWORD)

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

class ImageQueue():
    queue = "image_queue"
    
# This funciton should take path to original image as argument and pass the crop/resizing job to the image_queue
    @staticmethod
    def perform(path_to_original, username, user_id):
        final_path = PROJECT_ROOT+'/'+path_to_original
        avatar = Image.open(final_path)
        width, height = avatar.size
        if width > height:
            delta = width - height
            left = int(delta/2)
            upper = 0
            right = height + left
            lower = height
        else:
            delta = height - width
            left = int(delta)/2
            upper = 0
            right = width
            lower = width + upper
        avatar_square = avatar.crop((left, upper, right, lower))
        avatar_mini = copy.copy(avatar_square)
        avatar_square.thumbnail((48,48))
        avatar_mini.thumbnail((24,24))
        filename = username['username']+'.jpg'
        minifilename = username['username']+'_mini'+'.jpg'
        path_to_save = os.path.join(PROJECT_ROOT, 'static', 'avatars', filename)
        path_to_mininail = os.path.join(PROJECT_ROOT, 'static', 'avatars', minifilename)
        avatar_square.save(path_to_save)
        avatar_mini.save(path_to_mininail)
        database.execute("UPDATE user SET user_thumbnail=%s, user_mininail=%s WHERE id=%s", path_to_save, path_to_mininail, user_id)
        return True
        