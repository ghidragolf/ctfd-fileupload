import pika
import requests
import os
import json
import time
import random

def main():
    time.sleep(2)
    # Use the same AMQP as the CTFd docker image
    rabbit_url = os.environ.get("RABBITMQ_URL", "amqp://user:pass@rabbit:5672")
    q = os.environ.get("RABBITMQ_QUEUE", "ctfd")
    try:
        connection = pika.BlockingConnection(pika.URLParameters(rabbit_url))
        channel = connection.channel()
        channel.queue_declare(queue=q)
        channel.basic_consume(queue=q, auto_ack=True, on_message_callback=callback)
        print("[*] Waiting for messages")
        channel.start_consuming()
    except:
        time.sleep(10)
        main()

def callback(ch, method, properties, body):
    data = json.loads(body.decode("utf-8"))
    start = time.time()
    print(f"Got script: id={data.get('id')} challenge={data.get('challenge')} content={data.get('content')}\n\nExecuting...")
    time.sleep(random.randrange(1,7))

    # This sample runner always passes back "hello world" as the script output
    results = {
        "results": "hello world",
        "execution_time": time.time()-start
    }
    print(json.dumps(results))
    res = requests.post("http://ctfd:8000/api/v1/scripts/solve/"+data.get("id"), data=results)
    print(res.status_code, res.text)

main()
