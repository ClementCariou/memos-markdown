from urllib.parse import urljoin
import requests
import argparse
from dotenv import load_dotenv
import os
import shutil
import datetime


def safe_mkdirs(path):
    """Safely create directories, handling exceptions."""
    try:
        os.makedirs(path, exist_ok=True)
    except OSError as e:
        print(f"Error creating directory {path}: {e}")


def download_image(image_url, local_path, token):
    """Download an image and save it to a local path."""
    try:
        headers = {'Authorization': f'Bearer {token}'}
        response = requests.get(image_url, headers=headers, stream=True)
        if response.status_code == 200:
            with open(local_path, 'wb') as f:
                response.raw.decode_content = True
                shutil.copyfileobj(response.raw, f)
        else:
            print(f"Failed to fetch {image_url}. Status code: {
                  response.status_code}")
    except requests.RequestException as e:
        print(f"Request failed: {e}")


def create_markdown_files(data, out_dir, base_url, token):
    name_by_id = {}
    root_notes = []

    if os.path.exists(out_dir):
        shutil.rmtree(out_dir)
    safe_mkdirs(out_dir)
    assets_dir = os.path.join(out_dir, 'assets')
    safe_mkdirs(assets_dir)

    for entry in data:
        if 'name' not in entry or 'content' not in entry:
            continue

        if 'id' in entry:
            name_by_id[entry['id']] = entry['name']

        filename = f"{entry['name']}.md"
        file_path = os.path.join(out_dir, filename)

        with open(file_path, 'w', encoding="utf-8") as md_file:
            created_ts_readable, updated_ts_readable = parse_timestamps(
                entry)
            memo_id = entry.get('id', 'N/A')
            write_metadata(
                md_file, entry, created_ts_readable, updated_ts_readable)
            md_file.write(entry['content'])

            if 'resourceList' in entry and entry['resourceList']:
                for resource in entry['resourceList']:
                    process_resource(resource, base_url,
                                     assets_dir, out_dir, md_file, token)

            isRootNote = process_relations(
                entry, name_by_id, memo_id, md_file)
            if isRootNote:
                root_notes.append(entry)

    write_index_file(root_notes, name_by_id, out_dir)


def parse_timestamps(entry):
    """Parse creation and update timestamps."""
    created_ts_readable = datetime.datetime.fromtimestamp(int(entry.get(
        'createdTs', 'N/A'))).strftime('%Y-%m-%d %H:%M:%S') if entry.get('createdTs', 'N/A') != 'N/A' else 'N/A'
    updated_ts_readable = datetime.datetime.fromtimestamp(int(entry.get(
        'updatedTs', 'N/A'))).strftime('%Y-%m-%d %H:%M:%S') if entry.get('updatedTs', 'N/A') != 'N/A' else 'N/A'
    return created_ts_readable, updated_ts_readable


def write_metadata(md_file, entry, created_ts_readable, updated_ts_readable):
    """Write metadata to the markdown file."""
    md_file.write(f"---\n")
    for key in ['id', 'name', 'creatorId', 'visibility', 'creatorName']:
        md_file.write(f"{key}: {entry.get(key, 'N/A')}\n")
    md_file.write(f"createdTs: {created_ts_readable}\n")
    md_file.write(f"updatedTs: {updated_ts_readable}\n---\n\n")
    md_file.write(f"[[{entry.get('creatorName', 'N/A')
                       } - {created_ts_readable}]]({entry['name']})\n\n")


def process_resource(resource, base_url, assets_dir, out_dir, md_file, token):
    name = resource.get('name')
    filename = f"{resource.get('createdTs')}_{resource.get('filename')}"
    if name:
        image_url = urljoin(base_url, f"/o/r/{name}")
        local_image_path = os.path.join(assets_dir, filename)
        relative_path_to_image = os.path.relpath(local_image_path, out_dir)
        md_file.write(f"\n\n![{filename}]({relative_path_to_image})")
        download_image(image_url, local_image_path, token)


def process_relations(entry, name_by_id, memo_id, md_file):
    """Process relations and determine if the note is a root note."""
    isRootNote = True
    if 'relationList' in entry and entry['relationList']:
        comments = []
        for relation in entry['relationList']:
            memoId = relation.get('memoId')
            type = relation.get('type')
            isRootNote = memoId != memo_id or type != "COMMENT"
            if memoId and memoId in name_by_id and memoId != memo_id:
                related_note_name = name_by_id[memoId]
                comments.append(related_note_name)
        if comments:
            md_file.write(f"\n\n<details><summary>{len(comments)} comment{
                          's' if len(comments) > 1 else ''}</summary>\n")
            for comment in comments:
                md_file.write(f"\n![[{comment}]]")
            md_file.write("\n</details>")
    return isRootNote


def write_index_file(root_notes, name_by_id, out_dir):
    """Write the index file for all root notes."""
    index_file_path = os.path.join(out_dir, 'index.md')
    with open(index_file_path, 'w', encoding="utf-8") as index_file:
        index_file.write("# Memos\n\n")
        for root_note in root_notes:
            note_name = name_by_id.get(root_note['id'])
            if note_name:
                index_file.write(f"![[{note_name}]]\n")


def fetch_and_parse_json(base_url, path, token):
    headers = {'Authorization': f'Bearer {token}'}
    full_url = urljoin(base_url, path)
    try:
        response = requests.get(full_url, headers=headers)
        if response.status_code == 200:
            return response.json()
        else:
            print(f"Failed to fetch data. Status code: {response.status_code}")
            return None
    except requests.RequestException as e:
        print(f"Request failed: {e}")
        return None


if __name__ == "__main__":
    load_dotenv()
    parser = argparse.ArgumentParser(
        description='Fetch and parse JSON from a URL using a bearer token for authentication.')
    parser.add_argument('--url', type=str,
                        help='The URL to fetch the JSON from.')
    parser.add_argument('--token', type=str,
                        help='The Memos access token.')
    parser.add_argument('--out-dir', type=str,
                        help='The output directory for markdown files.')
    parser.add_argument('--memo-query', type=str,
                        help='The memo query string, e.g., "/api/v1/memo?creatorId=1"')
    args = parser.parse_args()

    url = args.url if args.url else os.getenv('URL')
    token = args.token if args.token else os.getenv('TOKEN')
    out_dir = args.out_dir if args.out_dir else os.getenv('OUT_DIR', 'out')
    memo_query = args.memo_query if args.memo_query else os.getenv(
        'MEMO_QUERY', '/api/v1/memo?creatorId=1')

    if not url or not token:
        print("URL and TOKEN are required.")
    else:
        data = fetch_and_parse_json(url, memo_query, token)
        if data is not None:
            create_markdown_files(data, out_dir, url, token)
