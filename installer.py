import os
import wget
import shutil
json_jar = wget.download('http://repo1.maven.org/maven2/org/json/json/20190722/json-20190722.jar')
tensorflow_jar = wget.download('http://storage.googleapis.com/tensorflow/libtensorflow/libtensorflow-1.14.0.jar')
print()
os.system('svn checkout http://github.com/drtnf/LoveLetter/trunk/src')
shutil.move('server', os.path.join('src', 'server'))
os.mkdir('Tensorflow-Config')
os.mkdir('bin')
os.rename(json_jar, 'json.jar')
os.rename(tensorflow_jar, 'libtensorflow.jar')
shutil.move('json.jar', os.path.join('bin','json.jar'))
shutil.move('libtensorflow.jar', os.path.join('bin','libtensorflow.jar'))
os.system('javac -cp bin/json.jar:bin/libtesorflow.jar -d bin src/*/*.java')
print('installer finished...')

