# Script Challenges Plugin

A CTFd plugin that allows competitors to upload scripts. The scripts are queued through RabbitMQ to be handled be a runner.

![](./img/solve.gif)

## Simple Configuration
If you would like a very simple deployment, and the fastest way to get up and running, you can set some simple enviroment varibles and have a basic script configuration ready to go.

| **Environment Variable** | **Default Value** | **Description** |
|--------------------------|-------------------|-----------------|
|`RABBITMQ_URL` |`amqp://user:pass@rabbit:5672`| [RabbitMQ configuration URL](https://pika.readthedocs.io/en/latest/modules/parameters.html#urlparameters) |
|`RABBITMQ_QUEUE`|`ctfd`|The queue that CTFd will send the scripts through|
|`EXECUTION_TIMEOUT`|`120` seconds  |Timeout (in seconds) for submissions to become invalid.|
|`ALLOWED_EXTENSIONS`|`.py;.java;.txt`|File extension list the the competitors are allowed to upload.|

By modifying these settings a basic deployment will be set up that passes upload scripts to the [example consumer](./consumer/README.md).

## Advanced Configuration
For more advanced deployment types, you will want to modify [./ctfd_script_challenges/config.py](). You can override all the settings mentioned above, as well as the `validate_file` function and the JSON data that is passed into RabbitMQ.

## Consumer

An example consumer has been provide for testing.
Note, The consumer within this repo is a **test Python script** for testing the CTFd-to-RabbitMQ integration.
For the actual consumer deployed, see [gg-consumer](https://github.com/ghidragolf/gg-consumer)

This consumer takes the script from RabbitMQ, and basic information about the challenge and user who sumbitted, and returns the results back to CTFd.

>Note: The example consumer does _NOT_ execute scripts and simply returns "hello world"

## Running

Run the CTFd stack with docker compose
```
$> docker-compose build
$> docker-compose up -d
```

### Creating Challenges

1. To create new script challenges in CTFd, select the "script" type and create your challenge as normal.


![](./img/challenge.png)

2. Create a new `multi` flag. Each line in this flag must be contained in the script results returned from the server.


![](./img/flag.png)


### Disclaimer
Executing untrusted user scripts can be dangerous. Make sure you validate the uploaded submissions and implement safeguards to prevent attacks. Always run execute the uploaded scripts on a different system than the CTFd server to ensure the integrity of the competition. see the [gg-consumer repo](https://github.com/ghidragolf/gg-consumer/tree/dev#defensive-measures-for-ghidra-golf-consumer) for strategies on defensive deployments.
