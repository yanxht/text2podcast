# =================================================================
# BLOB & TABLE STORAGE MANAGER
# Purpose: Handles file uploads (MP3/MD) and prevents duplicate processing.
# =================================================================

from azure.storage.blob import BlobServiceClient, ContentSettings
from azure.data.tables import TableClient
from azure.core.exceptions import ResourceNotFoundError
from datetime import datetime
import os
import json

def upload_to_blob(file_path, conn_str, container_name, content_type="audio/mpeg"):
    """
    Uploads a local file to Azure Blob Storage and sets the correct MIME type.
    Returns the public URL of the uploaded file for use in the RSS feed.
    """

    blob_service_client = BlobServiceClient.from_connection_string(conn_str)
    blob_name = os.path.basename(file_path)
    blob_client = blob_service_client.get_blob_client(container=container_name, blob=blob_name)
    
    with open(file_path, "rb") as data:
        blob_client.upload_blob(
            data, 
            overwrite=True, 
            content_settings=ContentSettings(content_type=content_type)
        )
    return blob_client.url

def check_and_mark_duplicate(subreddit, post_id, metadata, connection_string, table_name):
    """
    The 'Memory' of the bot. Checks Azure Table Storage for a PostID.
    If not found, it logs the post to ensure it isn't synthesized again.
    """
    
    try:
        table_client = TableClient.from_connection_string(
            conn_str=connection_string, 
            table_name=table_name
        )

        # Instead of get_table_properties, we just try to get the entity.
        # This acts as both a connection check and a duplicate check.
        try:
            table_client.get_entity(partition_key=subreddit, row_key=post_id)
            print(f"Post {post_id} already exists in Azure Table. Skipping.")
            return True
        except ResourceNotFoundError:
            # Post doesn't exist, so we mark it as processed now
            entity = {
                'PartitionKey': subreddit,
                'RowKey': post_id,
                'Title': metadata.get('Title', 'Unknown'),
                'UserId': metadata.get('UserId', 'Unknown'),
                'ProcessedTimestamp': metadata.get('CreateTime', 'Unknown')
            }
            table_client.create_entity(entity=entity)
            return False

    except Exception as e:
        print(f"⚠️ Azure Table Storage error: {e}")
        # If the table itself doesn't exist, you might need to create it:
        # table_service_client.create_table_if_not_exists(table_name)
        return False