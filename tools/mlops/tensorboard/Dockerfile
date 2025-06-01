FROM tensorflow/tensorflow:latest

RUN pip install --no-cache-dir tensorboard tensorflow-io[boto3]

EXPOSE 6006

ENTRYPOINT ["tensorboard"]
CMD ["--logdir", "s3://huggingface-datasets/english_quotes/training-logs", "--host", "0.0.0.0"]
