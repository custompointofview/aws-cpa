FROM python

WORKDIR /root

# setting up the environment
RUN pip3 install --no-cache-dir numpy scipy pandas matplotlib sklearn boto3 awscli

COPY cost-explorer.py /root

ENTRYPOINT ["python3", "cost-explorer.py", "--profile", "ALL"]