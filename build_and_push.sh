#!/bin/bash
#set -x

IMG="hf-downloader"
REPO="registry-sam.inria.fr:5000/aistuff"
B_DIR="/user/ptempier/home/docker_images/"
TAG="$(cat "$B_DIR/$IMG/.version")"

if [[ -z "$TAG" ]]
then
    TAG=0
fi

echo "
#==== Vars
IMG   : $IMG
REPO  : $REPO
B_DIR : $B_DIR
TAG   : $TAG
"

cd "$B_DIR/$IMG/"

echo "#==== git pull"
git pull

echo "#==== docker build"
docker build -t "$IMG:$TAG" .

echo "#==== docker tag"
docker tag "$IMG:$TAG" "$REPO/$IMG:$TAG" 
docker tag "$IMG:$TAG" "$REPO/$IMG:latest" 

echo "#==== docker push"
docker push "$REPO/$IMG:$TAG"
docker push "$REPO/$IMG:latest"

echo "#==== update version"
TAG=$(( $TAG + 1 ))
echo "$TAG" > "$B_DIR/$IMG/.version"
