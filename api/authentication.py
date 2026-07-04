from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError, AuthenticationFailed
import logging

logger = logging.getLogger(__name__)


class OptionalJWTAuthentication(JWTAuthentication):
    """
    JWT Authentication that doesn't raise exceptions for invalid tokens.
    This allows AllowAny views to work even with invalid/missing tokens.
    
    For IsAuthenticated views, invalid tokens will still result in 401,
    but AllowAny views will work without authentication.
    """
    
    def authenticate(self, request):
        """
        Authenticate the request and return a two-tuple of (user, token),
        or None if no authentication is provided or token is invalid.
        """
        header = self.get_header(request)
        if header is None:
            return None
        
        raw_token = self.get_raw_token(header)
        if raw_token is None:
            return None
        
        # Convert bytes to string if needed
        if isinstance(raw_token, bytes):
            raw_token = raw_token.decode('utf-8')
        
        # Check for common frontend errors
        if raw_token == 'undefined' or raw_token == 'null' or not raw_token or raw_token.strip() == '':
            logger.error(f"❌ Frontend sent invalid token: '{raw_token}' - token not stored in localStorage!")
            logger.error(f"   This means localStorage.getItem('access_token') returned undefined/null")
            logger.error(f"   Frontend needs to store token after login: localStorage.setItem('access_token', token)")
            return None
        
        # Log token details for debugging
        token_preview = raw_token[:50] + "..." if len(raw_token) > 50 else raw_token
        logger.info(f"🔐 Token received (length: {len(raw_token)}, preview: {token_preview})")
        
        try:
            validated_token = self.get_validated_token(raw_token)
            user = self.get_user(validated_token)
            logger.info(f"✅ Authentication successful for user {user.id}")
            return (user, validated_token)
        except AuthenticationFailed as e:
            # User not found or authentication failed
            logger.warning(f"❌ Authentication failed: {str(e)}")
            
            # Try to decode token to see what user_id it's trying to find
            try:
                import jwt
                from django.conf import settings
                decoded = jwt.decode(raw_token, options={"verify_signature": False})
                user_id = decoded.get('user_id')
                logger.warning(f"   Token contains user_id: {user_id}")
                logger.warning(f"   This user does not exist in the database")
                logger.warning(f"   User may have been deleted, or token is from a different database")
            except Exception as decode_error:
                logger.warning(f"   Could not decode token: {str(decode_error)}")
            
            # Don't raise exception - just return None (unauthenticated)
            # This allows AllowAny views to work without valid tokens
            # IsAuthenticated views will still get 401 from permission check
            return None
        except (InvalidToken, TokenError) as e:
            # Log detailed token errors for debugging
            logger.warning(f"❌ Token validation failed")
            logger.warning(f"   Token length: {len(raw_token)}")
            logger.warning(f"   Token preview: {token_preview}")
            logger.warning(f"   Error: {str(e)}")
            logger.warning(f"   Error type: {type(e).__name__}")
            
            # Try to decode token to see what's wrong
            try:
                import jwt
                from django.conf import settings
                decoded = jwt.decode(raw_token, options={"verify_signature": False})
                logger.warning(f"   Decoded token (without verification): {decoded}")
            except Exception as decode_error:
                logger.warning(f"   Could not decode token: {str(decode_error)}")
            
            # Don't raise exception - just return None (unauthenticated)
            # This allows AllowAny views to work without valid tokens
            # IsAuthenticated views will still get 401 from permission check
            return None
        except Exception as e:
            # Log unexpected errors
            logger.error(f"Unexpected authentication error: {str(e)}", exc_info=True)
            # For any other exception, also return None
            # This prevents crashes from unexpected authentication errors
            return None

