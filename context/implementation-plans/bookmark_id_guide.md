# Guide: Fetching Insights Bookmark IDs Using Service Account Authentication

This guide demonstrates how to programmatically retrieve Mixpanel Insights bookmark IDs using Service Account authentication with Python and the `httpx` library.



## Prerequisites



```python
pip install httpx
```

## Authentication Setup

Service Accounts use HTTP Basic Authentication. You'll need:



- Service Account Username
- Service Account Secret
- Project ID



```python
import httpx
import base64
from typing import List, Dict, Optional, Any

class MixpanelBookmarkClient:
    def __init__(self, 
                 service_account_username: str,
                 service_account_secret: str,
                 base_url: str = "https://mixpanel.com"):
        """
        Initialize the Mixpanel Bookmark API client.
        
        Args:
            service_account_username: Your Service Account username
            service_account_secret: Your Service Account secret
            base_url: Mixpanel API base URL (use https://eu.mixpanel.com for EU datacenter)
        """
        self.base_url = base_url
        self.auth = (service_account_username, service_account_secret)
        self.client = httpx.Client(auth=self.auth)
```

## API Endpoints

### Get Bookmarks for a Project



```python
def get_project_bookmarks(self,
                          project_id: int,
                          bookmark_type: Optional[str] = None,
                          bookmark_ids: Optional[List[int]] = None,
                          eligible_for_dashboard: bool = False,
                          api_version: int = 2) -> Dict[str, Any]:
    """
    Fetch bookmarks for a specific project.
    
    Args:
        project_id: The Mixpanel project ID
        bookmark_type: Filter by bookmark type. Options:
            - "insights": Insights reports
            - "funnels": Funnel reports
            - "retention": Retention reports
            - "flows": Flows reports
            - "segmentation3": Legacy segmentation reports
        bookmark_ids: List of specific bookmark IDs to retrieve
        eligible_for_dashboard: If True, only return bookmarks that can be added to dashboards
        api_version: API version (1 or 2). Version 2 recommended for better performance
    
    Returns:
        Dict containing the API response with bookmark data
    """
    endpoint = f"{self.base_url}/api/app/projects/{project_id}/bookmarks"
    
    params = {"v": api_version}
    
    if bookmark_type:
        params["type"] = bookmark_type
    
    if bookmark_ids:
        # API expects id[] format for multiple IDs
        for bookmark_id in bookmark_ids:
            params[f"id[]"] = bookmark_id
    
    if eligible_for_dashboard:
        params["eligible_for_dashboard"] = "true"
    
    response = self.client.get(endpoint, params=params)
    response.raise_for_status()
    
    return response.json()
```

### Get Bookmarks for a Workspace



```python
def get_workspace_bookmarks(self,
                            workspace_id: int,
                            bookmark_type: Optional[str] = None,
                            bookmark_ids: Optional[List[int]] = None,
                            eligible_for_dashboard: bool = False,
                            api_version: int = 2) -> Dict[str, Any]:
    """
    Fetch bookmarks for a specific workspace.
    
    Args:
        workspace_id: The Mixpanel workspace ID
        bookmark_type: Filter by bookmark type (same options as get_project_bookmarks)
        bookmark_ids: List of specific bookmark IDs to retrieve
        eligible_for_dashboard: If True, only return bookmarks that can be added to dashboards
        api_version: API version (1 or 2)
    
    Returns:
        Dict containing the API response with bookmark data
    """
    endpoint = f"{self.base_url}/api/app/workspaces/{workspace_id}/bookmarks"
    
    params = {"v": api_version}
    
    if bookmark_type:
        params["type"] = bookmark_type
    
    if bookmark_ids:
        for bookmark_id in bookmark_ids:
            params[f"id[]"] = bookmark_id
    
    if eligible_for_dashboard:
        params["eligible_for_dashboard"] = "true"
    
    response = self.client.get(endpoint, params=params)
    response.raise_for_status()
    
    return response.json()
```

## Response Structure

### API v2 Response Format



```python
# Type definitions for clarity
from dataclasses import dataclass
from datetime import datetime

@dataclass
class BookmarkResponse:
    """Structure of a bookmark in the API v2 response"""
    id: int                          # The bookmark ID (use this for query API)
    name: str                        # Display name of the bookmark
    type: str                        # "insights", "funnels", "retention", etc.
    params: Dict[str, Any]           # Bookmark configuration/query parameters
    icon: Optional[str]              # Icon identifier
    description: Optional[str]       # Bookmark description
    created: datetime                # Creation timestamp
    modified: datetime               # Last modification timestamp
    user_id: int                     # Creator's user ID
    last_modified_by_id: int         # ID of user who last modified
    project_id: int                  # Associated project ID
    workspace_id: Optional[int]      # Associated workspace ID (if applicable)
    dashboard_id: Optional[int]      # Parent dashboard ID (if linked to dashboard)
    is_private: bool                 # Visibility flag
    is_restricted: bool              # Edit restriction flag
    can_edit: bool                   # Current user's edit permission
    can_view: bool                   # Current user's view permission
```

## Complete Working Example



```python
import httpx
from typing import List, Dict, Optional, Any
import json

class MixpanelBookmarkAPI:
    def __init__(self, username: str, secret: str, base_url: str = "https://mixpanel.com"):
        self.client = httpx.Client(
            auth=(username, secret),
            base_url=base_url,
            timeout=30.0
        )
    
    def get_insights_bookmarks(self, project_id: int) -> List[Dict[str, Any]]:
        """
        Fetch all Insights bookmarks for a project.
        
        Returns:
            List of bookmark dictionaries containing id, name, and params
        """
        try:
            response = self.client.get(
                f"/api/app/projects/{project_id}/bookmarks",
                params={
                    "type": "insights",
                    "v": 2  # Use API v2 for better performance
                }
            )
            response.raise_for_status()
            
            data = response.json()
            return data.get("results", [])
            
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise Exception("Authentication failed. Check your Service Account credentials.")
            elif e.response.status_code == 403:
                raise Exception(f"Access denied. Service Account lacks permission for project {project_id}")
            else:
                raise Exception(f"HTTP error {e.response.status_code}: {e.response.text}")
    
    def get_bookmark_by_id(self, project_id: int, bookmark_id: int) -> Optional[Dict[str, Any]]:
        """
        Fetch a specific bookmark by ID.
        
        Returns:
            Bookmark dictionary or None if not found
        """
        response = self.client.get(
            f"/api/app/projects/{project_id}/bookmarks",
            params={
                "id[]": bookmark_id,
                "v": 2
            }
        )
        response.raise_for_status()
        
        results = response.json().get("results", [])
        return results[0] if results else None
    
    def extract_bookmark_ids(self, bookmarks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Extract relevant information from bookmarks for use with Query API.
        
        Returns:
            List of dicts with id, name, and key parameters
        """
        extracted = []
        for bookmark in bookmarks:
            extracted.append({
                "bookmark_id": bookmark["id"],  # Use this with /api/query/insights
                "name": bookmark["name"],
                "type": bookmark["type"],
                "created": bookmark.get("created"),
                "modified": bookmark.get("modified"),
                "dashboard_id": bookmark.get("dashboard", {}).get("id") if bookmark.get("dashboard") else None
            })
        return extracted
    
    def close(self):
        """Close the HTTP client connection."""
        self.client.close()

# Usage Example
def main():
    # Initialize the client
    client = MixpanelBookmarkAPI(
        username="your-service-account-username",
        secret="your-service-account-secret"
    )
    
    project_id = 12345
    
    try:
        # Fetch all Insights bookmarks
        print("Fetching Insights bookmarks...")
        bookmarks = client.get_insights_bookmarks(project_id)
        print(f"Found {len(bookmarks)} Insights bookmarks")
        
        # Extract bookmark IDs for use with Query API
        bookmark_info = client.extract_bookmark_ids(bookmarks)
        
        # Display the bookmark IDs
        for info in bookmark_info:
            print(f"\nBookmark: {info['name']}")
            print(f"  ID: {info['bookmark_id']}")
            print(f"  Type: {info['type']}")
            print(f"  Modified: {info['modified']}")
        
        # Now you can use these IDs with the Query API
        if bookmark_info:
            first_bookmark_id = bookmark_info[0]['bookmark_id']
            print(f"\nExample Query API call:")
            print(f"POST https://mixpanel.com/api/query/insights")
            print(f"Body: {{\"bookmark_id\": {first_bookmark_id}}}")
    
    finally:
        client.close()

if __name__ == "__main__":
    main()
```

## Using Bookmark IDs with the Query API

Once you have the bookmark IDs, you can use them with the Query API:





```python
def query_insights_bookmark(self, bookmark_id: int, 
                           additional_params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Execute a saved Insights report using its bookmark ID.
    
    Args:
        bookmark_id: The bookmark ID obtained from get_insights_bookmarks()
        additional_params: Optional parameters to override bookmark defaults
            (e.g., date ranges, filters)
    
    Returns:
        Query results from the Insights API
    """
    endpoint = f"{self.base_url}/api/query/insights"
    
    payload = {"bookmark_id": bookmark_id}
    if additional_params:
        payload.update(additional_params)
    
    response = self.client.post(
        endpoint,
        json=payload,
        headers={"Content-Type": "application/json"}
    )
    response.raise_for_status()
    
    return response.json()

# Example usage
results = client.query_insights_bookmark(
    bookmark_id=123456,
    additional_params={
        "from_date": "2024-01-01",
        "to_date": "2024-01-31"
    }
)
```

## Error Handling



```python
class MixpanelAPIError(Exception):
    """Base exception for Mixpanel API errors"""
    pass

class AuthenticationError(MixpanelAPIError):
    """Raised when authentication fails (401)"""
    pass

class PermissionError(MixpanelAPIError):
    """Raised when access is denied (403)"""
    pass

class BookmarkNotFoundError(MixpanelAPIError):
    """Raised when a bookmark is not found (404)"""
    pass

# Enhanced error handling in the client
try:
    bookmarks = client.get_insights_bookmarks(project_id)
except httpx.HTTPStatusError as e:
    if e.response.status_code == 401:
        raise AuthenticationError("Invalid Service Account credentials")
    elif e.response.status_code == 403:
        raise PermissionError(f"Service Account lacks access to project {project_id}")
    elif e.response.status_code == 404:
        raise BookmarkNotFoundError("Bookmark or project not found")
    else:
        raise MixpanelAPIError(f"API error: {e.response.status_code} - {e.response.text}")
```

## Best Practices

1. **Use API v2** - Set `v=2` parameter for better performance and response format
2. **Filter by type** - Use `type="insights"` to only get Insights bookmarks
3. **Handle pagination** - For projects with many bookmarks, results are batched (10,000 per batch internally)
4. **Cache bookmark IDs** - Bookmark IDs are stable; cache them to reduce API calls
5. **Use connection pooling** - Reuse the `httpx.Client` instance for multiple requests
6. **Set appropriate timeouts** - Use reasonable timeouts (30 seconds recommended)
7. **Implement retry logic** - Add exponential backoff for transient failures

This comprehensive approach allows you to programmatically discover and use bookmark IDs without manually extracting them from the Mixpanel UI.