import tornado.httpserver
import tornado.ioloop
import tornado.web
import tornado.database
import tornado.escape
import tornado.auth
import os
import logging
import PIL 
from PIL import Image
import imghdr
import StringIO
from tornado.options import define, options
from hashlib import md5
import copy
from pyres import ResQ
from tasks import *
from settings import *

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
r = ResQ()
   
define("port", default=8888, help="run on the given port", type=int)
define("mysql_host", default=MYSQL_HOST, help="database host")
define("mysql_database", default=MYSQL_DATABASE, help="dataabase name")
define("mysql_user", default=MYSQL_USER, help="database user")
define("mysql_password", default=MYSQL_PASSWORD, help="database password")
 
class Application(tornado.web.Application):
    def __init__(self):
        handlers = [
            (r"/", MainHandler),
            (r"/login", LoginHandler),
            (r"/follow", FollowHandler),
            (r"/unfollow", UnfollowHandler),
            (r"/image", ImageHandler),
            (r"/logout", LogoutHandler),
            (r"/([\w\.\-]+)", UserHandler),
            # (r"/entry/([^/]+)", EntryHandler),
            # (r"/compose", ComposeHandler),
            #(r"/auth/login", AuthLoginHandler),
        ]
        settings = dict(
            template_path=os.path.join(os.path.dirname(__file__), "templates"),
            static_path=os.path.join(os.path.dirname(__file__), "static"),
            xsrf_cookies=True,
            cookie_secret="11oETzKXQAGaYdkL5gEmGeJJFuYh7EQnp2XdTP1o/Vo=",
            login_url="/login",
        )
        tornado.web.Application.__init__(self, handlers, **settings)
        self.db = tornado.database.Connection(
            host=options.mysql_host, database=options.mysql_database,
            user=options.mysql_user, password=options.mysql_password)
    
            
class BaseHandler(tornado.web.RequestHandler):
    @property
    def db(self):
        return self.application.db

    def get_current_user(self):
        return self.get_secure_cookie("user_id")

class MainHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self):
        user_id=self.current_user
        following_tweets=self.db.query("SELECT tweet.content,tweet.pub_date,user.username,user.user_thumbnail FROM tweet,follow,user WHERE follow.dest_id=tweet.user_id AND follow.src_id=%s AND user.id=tweet.user_id ORDER BY tweet.pub_date DESC", user_id)
        following_users=self.db.query("SELECT * from user where id in (SELECT dest_id from follow WHERE src_id=%s)", user_id)
        return self.render("tweet.html", tweets=following_tweets, following_users=following_users)
        
    @tornado.web.authenticated    
    def post(self):
        content=self.get_argument("content", None)
        user_id=self.current_user
        self.db.execute("INSERT INTO tweet(content,pub_date,user_id) VALUES (%s,UTC_TIMESTAMP(),%s)",content,user_id)
        self.write(tornado.escape.json_encode({'status': 'success'}))
        
class LoginHandler(BaseHandler):
    def get(self):
        self.render("login.html")
        
    def post(self):
        username=str(self.get_argument("username", None))
        password=str(self.get_argument("password", None))
        if username and password:
            m=md5()
            m.update(password)
            encode_pass=m.hexdigest()
            result=self.db.get("SELECT id,username FROM user WHERE username=%s AND password=%s", username,encode_pass)
            if result:
                current_user=str(result['username'])
                self.set_secure_cookie('user_id', str(result['id']))
                return self.redirect("/")
            else:
                return self.write("Please enter valid username and password")
        else:
            return self.write("Please enter valid username and password")

class LogoutHandler(BaseHandler):
    def get(self):
        self.clear_all_cookies()
        self.redirect("/")

class UserHandler(BaseHandler):
    def get(self, username):
        follow_flag=None
        if self.current_user:
            src_id = self.current_user 
            follow_flag = self.db.get("SELECT active from follow,user WHERE follow.src_id=%s AND follow.dest_id=user.id AND user.username=%s",src_id, username)
            try:
                follow_flag = follow_flag['active']
            except:
                follow_flag = follow_flag
        output = self.db.get("SELECT username from user WHERE username=%s LIMIT 1", username)
        if not output: raise tornado.web.HTTPError(404)
        user_tweets=self.db.query("SELECT content FROM tweet,user WHERE tweet.user_id=user.id AND user.username=%s ORDER BY pub_date DESC", username)
        tweets=[]
        for item in user_tweets: tweets.append(item['content'])
        return self.render("user.html", tweets=tweets, username=username, follow_flag=follow_flag)
    
       
class FollowHandler(BaseHandler):
    @tornado.web.authenticated
    def post(self):
        src_id = self.current_user
        dest_name = self.get_argument("dest_name", None)
        dest_id = self.db.get("SELECT id FROM user WHERE username=%s", dest_name)
        if not dest_id: return self.finish({'status':'fail','message': 'Invalid User'})
        result = self.db.get("SELECT active from follow WHERE src_id=%s AND dest_id=%s", src_id,dest_id['id'])
        if result and result['active'] == 0:
            self.db.execute("UPDATE follow SET active=1 WHERE src_id=%s AND dest_id=%s", src_id,dest_id['id'])
        else:    
            self.db.execute("INSERT INTO follow(src_id,dest_id,active) VALUES (%s,%s,%s)", src_id,dest_id['id'],1)
        return self.finish({'status': 'success', 'message': 'You are following '+dest_name})

class UnfollowHandler(BaseHandler):
    @tornado.web.authenticated
    def post(self):
        src_id = self.current_user
        dest_name = self.get_argument("dest_name", None)
        dest_id = self.db.get("SELECT id FROM user WHERE username=%s", dest_name)
        if not dest_id: return self.finish({'status':'fail','message': 'Invalid User'})
        self.db.execute("UPDATE follow SET active=0 WHERE src_id=%s AND dest_id=%s", src_id,dest_id['id'])
        return self.finish({'status': 'success', 'message': 'You are not following '+dest_name})

class ImageHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self):
        return self.render("image.html")
    
# Saving the original image to the disk on static/uploaded_images with username_original.jpg as filename.       
    @tornado.web.authenticated
    def post(self):
        user_id=self.current_user
        username = self.db.get("SELECT username from user WHERE id=%s", user_id)
        uploaded_image=self.request.files
        if imghdr.what('ignore', uploaded_image['avatar'][0]['body']) in ['jpeg','png']:
            avatar = Image.open(StringIO.StringIO(uploaded_image['avatar'][0]['body']))
            uploaded_filename = username['username']+'_original'+'.jpg'
            path_to_original = os.path.join('static','uploaded_images', uploaded_filename)
            avatar.save(path_to_original)
            r.enqueue(ImageQueue, path_to_original, username, user_id)
            return self.write("Successfully uploaded the image")
        else: return self.write("file format is not accepted")
       
        
if __name__ == "__main__":
    http_server = tornado.httpserver.HTTPServer(Application())
    http_server.listen(8888)
    tornado.ioloop.IOLoop.instance().start()