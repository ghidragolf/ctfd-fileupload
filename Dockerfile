FROM ctfd/ctfd:latest

# Install pika as root
COPY requirements.txt /tmp/requirements.txt
USER root
RUN pip install -r /tmp/requirements.txt
USER ctfd
COPY ctfd_script_challenges /opt/CTFd/CTFd/plugins/ctfd_script_challenges