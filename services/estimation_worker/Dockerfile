FROM cwaffles/openpose AS openpose
WORKDIR /openpose/build/python/openpose
RUN make install

RUN cp ./pyopenpose.cpython-36m-x86_64-linux-gnu.so /usr/local/lib/python3.6/dist-packages
WORKDIR /usr/local/lib/python3.6/dist-packages
RUN ln -s pyopenpose.cpython-36m-x86_64-linux-gnu.so pyopenpose
RUN export LD_LIBRARY_PATH=/openpose/build/python/openpose
# python setuptools
RUN apt-get install python3-setuptools -y

WORKDIR /app


COPY ./services/web/requirements.txt /app/requirements.txt
RUN pip3 install -r /app/requirements.txt

COPY ./services/web/ /app
ENV FLASK_APP=manage.py
ENV FLASK_ENV=development
ENV LC_ALL=C.UTF-8
ENV LANG=C.UTF-8


CMD python3 manage.py run_worker