# Stratus needs the Terraform binary as well as Python, so the image is
# built in two stages: fetch Terraform, then copy just the binary into a
# slim Python image. Installing it with a package manager would drag in an
# apt cache and a signing key for a single 100MB file.
FROM hashicorp/terraform:1.15 AS terraform

FROM python:3.12-slim

COPY --from=terraform /bin/terraform /usr/local/bin/terraform

WORKDIR /app

# Dependencies first, so a code change does not re-download them.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY stratus/ ./stratus/

# One shared copy of the Azure provider rather than one per workspace.
ENV TF_PLUGIN_CACHE_DIR=/tmp/tf-plugins
RUN mkdir -p /tmp/tf-plugins

# Run as a non-root user. This process shells out to Terraform, which builds
# real infrastructure; there is no reason for it to also be root inside its
# own container.
RUN useradd --create-home stratus && chown -R stratus /app /tmp/tf-plugins
USER stratus

EXPOSE 8000

# Honour the platform's port. App Service, Container Apps, Render and Fly
# all inject one, and ignoring it is the most common reason a container
# starts fine and is never reachable.
CMD ["sh", "-c", "uvicorn stratus.web:app --host 0.0.0.0 --port ${PORT:-8000}"]
