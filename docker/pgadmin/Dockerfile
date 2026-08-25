# syntax=docker/dockerfile:1

FROM dpage/pgadmin4:latest

# The pgAdmin image already runs as a non-root user
# with fixed UID/GID 5050:5050 (there's no /etc/passwd
# entry named "pgadmin", so we must reference it numerically).
# On Render, mounted disks are owned by root by default, which
# blocks pgAdmin from writing its session/config data. Fix
# ownership at build time and make sure we stay on that user.
USER root
RUN chown -R 5050:5050 /var/lib/pgadmin

USER 5050

# pgAdmin detects non-root/restricted environments (like Render)
# and automatically switches its internal listen port from 80 to
# 8080 in that case. Expose 8080 so it matches what the process
# actually binds to at runtime.
EXPOSE 8080