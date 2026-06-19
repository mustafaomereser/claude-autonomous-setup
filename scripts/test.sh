#!/bin/bash

echo "Running tests..."
phpunit || exit 1
echo "OK"
