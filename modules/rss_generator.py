# =================================================================
# RSS FEED GENERATOR
# Purpose: Maintains the Podcast XML feed using iTunes-compliant tags.
# =================================================================

import os
import logging
from datetime import datetime
import xml.etree.ElementTree as ET
from azure.storage.blob import BlobClient, ContentSettings

# Define namespaces globally
ITUNES_NS = "http://www.itunes.com/dtds/podcast-1.0.dtd"
ET.register_namespace('itunes', ITUNES_NS)

def generate_item_description(post_data):
    """Creates a formatted HTML/Text show note including author and original URL."""

    header = (
        f"👤 Author: u/{post_data.get('UserId', 'Unknown')}\n"
        f"📂 Subreddit: r/{post_data.get('Subreddit', 'Unknown')}\n"
        f"📅 Date: {post_data.get('Created', 'Unknown')}\n"
        f"🔗 Post: {post_data.get('URL', '#')}\n"
        f"{'-'*30}\n\n"
    )
    content = post_data.get('CleanContent', '')
    return header + content

def update_rss_feed(connection_string, container_name, new_post_data):
    """
    1. Downloads the existing feed.xml from Azure.
    2. Appends the new episode as the top <item>.
    3. Re-uploads the updated XML to storage.
    Note: Registers 'itunes' namespaces to ensure podcast app compatibility.
    """

    blob_name = "feed.xml"
    blob_client = BlobClient.from_connection_string(connection_string, container_name, blob_name)
    
    # 1. Attempt to download existing feed
    try:
        logging.info("Downloading existing feed.xml...")
        xml_data = blob_client.download_blob().readall()
        root = ET.fromstring(xml_data)
        channel = root.find("channel")
    except Exception:
        logging.warning("Creating new feed skeleton.")
        # Create root WITHOUT manual xmlns attribute (register_namespace handles it)
        root = ET.Element("rss", version="2.0")
        channel = ET.SubElement(root, "channel")
        
        # Channel Metadata
        ET.SubElement(channel, "title").text = "My Private Reddit Podcast"
        ET.SubElement(channel, "description").text = "Personalized AI-generated stories from Reddit"
        ET.SubElement(channel, "link").text = f"https://{blob_client.account_name}.blob.core.windows.net/{container_name}"
        ET.SubElement(channel, "language").text = "en-us"

    # 2. Add the New Episode Item
    item = ET.SubElement(channel, "item")
    ET.SubElement(item, "title").text = new_post_data.get("Title", "Untitled Episode")
    ET.SubElement(item, "link").text = new_post_data.get("URL", "")
    
    description_text = generate_item_description(new_post_data)
    ET.SubElement(item, "description").text = description_text
    
    ET.SubElement(item, "guid", isPermaLink="false").text = new_post_data.get("PostId")
    ET.SubElement(item, "pubDate").text = datetime.now().strftime("%a, %d %b %Y %H:%M:%S GMT")
    
    # Use the namespace constant for iTunes tags
    ET.SubElement(item, f"{{{ITUNES_NS}}}author").text = new_post_data.get("UserId", "Unknown")
    ET.SubElement(item, f"{{{ITUNES_NS}}}summary").text = f"Reddit story from r/{new_post_data.get('Subreddit')}"
    
    # 3. Audio Enclosure
    ET.SubElement(item, "enclosure", {
        "url": new_post_data.get("MP3_URL"),
        "type": "audio/mpeg",
        "length": "0" 
    })

    # 4. Convert to string and Upload
    # The 'xml_declaration' and 'encoding' are vital for podcast apps
    updated_xml = ET.tostring(root, encoding="utf-8", method="xml", xml_declaration=True)
    
    content_settings = ContentSettings(content_type='application/xml')
    blob_client.upload_blob(updated_xml, overwrite=True, content_settings=content_settings)
    
    return f"https://{blob_client.account_name}.blob.core.windows.net/{container_name}/feed.xml"