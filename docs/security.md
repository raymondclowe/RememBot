# RememBot Security Configuration

## Web Interface Security

The RememBot web interface includes several security features that can be configured:

### Session Secret Key

**Important**: For production deployments, you must set a secure session secret key:

```bash
export SESSION_SECRET_KEY="your-long-random-secret-key-here"
```

If running in production mode (ENV=production), RememBot will refuse to start with the default key.

### Authentication Tokens

Web authentication tokens are single-use for security:
- Generated via `/web` command in Telegram
- 24-hour expiration time
- Automatically invalidated after first use
- Secure random generation (32-byte URL-safe)

### Environment Variables

For production deployment, configure these environment variables:

```bash
# Required for production
SESSION_SECRET_KEY="your-secure-random-key"

# Optional configurations
REMEMBOT_DATABASE_PATH="/path/to/your/database.db"
ENV="production"  # Enables production security checks
```

### Database Security

- SQLite database with user isolation
- All user data segregated by Telegram User ID
- No cross-user data access possible
- Local storage only (no cloud dependencies)

### Network Security

- Web interface binds to localhost (127.0.0.1) by default
- Use reverse proxy (nginx) for external access
- HTTPS recommended for production deployments
- No external network connections except for AI APIs (optional)

## Deployment Recommendations

1. **Use HTTPS**: Always deploy behind HTTPS in production
2. **Firewall**: Restrict database file access to RememBot user only
3. **Backup**: Regular encrypted backups of database file
4. **Updates**: Keep dependencies updated via `uv sync`
5. **Monitoring**: Monitor logs for authentication failures