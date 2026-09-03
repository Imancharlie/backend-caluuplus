"""Tile proxy to fetch OpenStreetMap tiles and serve with CORS headers.

This solves CORS issues when the frontend tries to fetch tiles directly from
OpenStreetMap servers, which don't send proper CORS headers.
"""

import logging
import requests
from django.http import HttpResponse, JsonResponse
from django.views.decorators.cache import cache_page
from django.views.decorators.http import require_GET

logger = logging.getLogger(__name__)


@require_GET
@cache_page(60 * 60 * 24)  # Cache tiles for 24 hours
def tile_proxy(request, z, x, y):
    """Proxy OpenStreetMap tile requests with proper CORS headers.
    
    Usage: /api/map/tiles/{z}/{x}/{y}.png
    Example: /api/map/tiles/20/638489/544081.png
    """
    try:
        # Validate zoom level (OSM supports 0-19)
        z = int(z)
        x = int(x)
        y = int(y)
        
        if not (0 <= z <= 19):
            return JsonResponse({"error": "Invalid zoom level. Must be between 0 and 19."}, status=400)
        
        # Fetch tile from OpenStreetMap
        tile_url = f"https://tile.openstreetmap.org/{z}/{x}/{y}.png"
        
        headers = {
            "User-Agent": "Caluu+ Map Proxy (https://caluu.plus)"
        }
        
        response = requests.get(tile_url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            # Return the tile image with CORS headers
            tile_response = HttpResponse(
                response.content,
                content_type="image/png"
            )
            tile_response["Access-Control-Allow-Origin"] = "*"
            tile_response["Access-Control-Allow-Methods"] = "GET, OPTIONS"
            tile_response["Access-Control-Allow-Headers"] = "*"
            tile_response["Cache-Control"] = "public, max-age=86400"  # 24 hours
            return tile_response
        else:
            logger.error(f"Failed to fetch tile: {tile_url} - Status: {response.status_code}")
            return JsonResponse(
                {"error": f"Failed to fetch tile from OpenStreetMap. Status: {response.status_code}"},
                status=response.status_code
            )
            
    except requests.exceptions.Timeout:
        logger.error(f"Timeout fetching tile: {tile_url}")
        return JsonResponse({"error": "Tile server timeout"}, status=504)
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching tile: {e}")
        return JsonResponse({"error": "Failed to fetch tile from tile server"}, status=502)
    except ValueError:
        return JsonResponse({"error": "Invalid tile coordinates"}, status=400)
    except Exception as e:
        logger.error(f"Unexpected error in tile proxy: {e}")
        return JsonResponse({"error": "Internal server error"}, status=500)


@require_GET
def tile_proxy_options(request):
    """Handle OPTIONS preflight requests for CORS."""
    response = HttpResponse()
    response["Access-Control-Allow-Origin"] = "*"
    response["Access-Control-Allow-Methods"] = "GET, OPTIONS"
    response["Access-Control-Allow-Headers"] = "*"
    response["Access-Control-Max-Age"] = "86400"
    return response
