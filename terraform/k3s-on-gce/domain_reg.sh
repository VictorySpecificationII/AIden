#!/bin/bash

# Load environment variables from file
source .env

# GoDaddy API credentials
API_KEY="$GODADDY_API_KEY"
API_SECRET="$GODADDY_API_SECRET"
DOMAIN="$GODADDY_DOMAIN"
RECORD_TYPE="A"
TTL=600

# Associative array mapping domains to IP addresses
declare -A DOMAIN_IP_MAPPING=(
    ["subdomain1"]="x.x.x.x"
    ["subdomain2"]="x.x.x.x"
    ["subdomain3"]="x.x.x.x"
)

# Loop through the domains and their corresponding IP addresses
for DOMAIN_NAME in "${!DOMAIN_IP_MAPPING[@]}"; do
    IP_ADDRESS="${DOMAIN_IP_MAPPING[$DOMAIN_NAME]}"
    
    # Create DNS record payload
    PAYLOAD='[{"data": "'$IP_ADDRESS'", "name": "'$DOMAIN_NAME'", "ttl": '$TTL', "type": "'$RECORD_TYPE'"}]'

    # Create DNS record using GoDaddy API
    curl -X PATCH "https://api.godaddy.com/v1/domains/$DOMAIN/records" \
         -H "accept: application/json" \
         -H "Content-Type: application/json" \
         -H "Authorization: sso-key $API_KEY:$API_SECRET" \
         -d "$PAYLOAD"
done
