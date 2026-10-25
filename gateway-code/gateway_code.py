import json
import logging
import os

import boto3 

logger = logging.getLogger()
logger.setLevel(logging.INFO)

KB_ID_PARAM = os.environ["KB_ID_PARAM"]
NUM_RESULTS = int(os.environ.get("NUM_RESULTS","5"))
LOG_RETRIEVED_CHUNKS = os.environ.get("LOG_RETRIEVED_CHUNKS", "false").lower() == "true"

ssm = boto3.client("ssm")
bedrock = boto3.client("bedrock-agent-runtime")

_KB_ID = None

def get_KB_ID():
    global _KB_ID
    if not _KB_ID:
        resp = ssm.get_parameter(Name=KB_ID_PARAM,WithDecryption=True)
        _KB_ID = resp["Parameter"]["Value"]
        logger.info("Loaded KB ID from SSM Parameter %s",_KB_ID)
    return _KB_ID

def lambda_handler(event,context):
    logger.info("event:%s",json.dumps(event))
    query = event.get("query")
    if not query:
        return {"error":"missing field : query"}
    
    response = bedrock.retrieve(
        knowledgeBaseId=get_KB_ID(),
        retrievalQuery={"text": query},
        retrievalConfiguration={
            "managedSearchConfiguration": {"numberOfResults": NUM_RESULTS}
        },
    )
 
    # Trim the large KB response down to what the model actually needs
    results = []
    
    for r in response.get("retrievalResults", []):
        location = r.get("location", {})
        results.append(
            {
                "text": r.get("content", {}).get("text"),
                "score": r.get("score"),
                "source": location.get("s3Location", {}).get("uri"),
            }
        )

    if LOG_RETRIEVED_CHUNKS:
        for index, result in enumerate(results, start=1):
            logger.info(
                "Retrieved chunk %d/%d (score=%s, source=%s): %s",
                index,
                len(results),
                result["score"],
                result["source"],
                result["text"],
            )
 
    # The return value becomes the tool result the agent receives
    return {"results": results}