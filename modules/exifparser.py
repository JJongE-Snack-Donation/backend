from datetime import datetime
import exifread
from PIL import Image
import os
import logging

# 로깅 설정
logging.basicConfig(level=logging.INFO)

# 그룹화 기준 (분 단위)
GROUP_TIME_LIMIT = 5

def parse_exif_data(image_path, project_info, analysis_folder, session_id):
    """이미지 파일에서 EXIF 데이터를 추출하는 함수"""
    try:
        with open(image_path, 'rb') as f:
            tags = exifread.process_file(f)

        # EXIF 데이터 추출
        date_time = str(tags.get('EXIF DateTimeOriginal', ''))
        if date_time:
            date_obj = datetime.strptime(date_time, '%Y:%m:%d %H:%M:%S')
        else:
            date_obj = datetime.now()

        # 파일명 생성 (YYYYMMDD-HHmmss 형식)
        seq = 1  # 시퀀스 번호
        filename = date_obj.strftime('%Y%m%d-%H%M%S') + f's{seq}.jpg'

        serial_number = str(tags.get('EXIF SerialNumber', 'UNKNOWN'))

        # 파일 경로 구성
        file_path = f"./mnt/{project_info['_id']}/{analysis_folder}/source/{filename}"
        thumbnail_path = f"./mnt/{project_info['_id']}/{analysis_folder}/thumbnail/thum_{filename}"

        # EXIF 정보 구성
        exif_data = {
            "FileName": filename,
            "FilePath": file_path,
            "OriginalFileName": os.path.basename(image_path),
            "ThumnailPath": thumbnail_path,
            "SerialNumber": serial_number,
            "UserLabel": str(tags.get('EXIF UserLabel', 'UNKNOWN')),
            "DateTimeOriginal": {
                "$date": date_obj.isoformat(timespec='milliseconds') + 'Z'
            },
            "ProjectInfo": {
                "ProjectName": project_info['name'],
                "ID": project_info['id']
            },
            "AnalysisFolder": analysis_folder,
            "sessionid": [session_id],
            "uploadState": "uploaded",
            "serial_filename": f"{serial_number}_{filename}",
            "__v": 0
        }

        logging.info(f"EXIF data parsed successfully for {image_path}")
        return exif_data

    except Exception as e:
        logging.error(f"Error parsing EXIF data for {image_path}: {str(e)}")
        return None

def assign_evtnum_to_group(images, evt_num):
    """이미지 그룹에 evtnum 할당"""
    for img in images:
        img['evtnum'] = evt_num
    return images

def group_images_by_time(image_list):
    """시간 기준으로 이미지를 그룹화하고 evtnum 할당"""
    result = []
    evt_num = 1

    grouped_by_serial = {}
    for img in image_list:
        key = f"{img['SerialNumber']}_{img['FileName']}"
        grouped_by_serial.setdefault(key, []).append(img)

    for group in grouped_by_serial.values():
        sorted_group = sorted(group, key=lambda x: x['DateTimeOriginal']['$date'])
        base_time = None
        current_group = []

        for img in sorted_group:
            current_time = datetime.fromisoformat(img['DateTimeOriginal']['$date'].replace('Z', ''))
            if not base_time or (current_time - base_time).total_seconds() / 60 <= GROUP_TIME_LIMIT:
                current_group.append(img)
            else:
                result.extend(assign_evtnum_to_group(current_group, evt_num))
                current_group = [img]
                base_time = current_time
                evt_num += 1

        if current_group:
            result.extend(assign_evtnum_to_group(current_group, evt_num))
            evt_num += 1

    return result

def process_images(image_paths, project_info, analysis_folder, session_id):
    """이미지 목록을 처리하고 MongoDB 저장용 데이터 생성"""
    image_data_list = []

    for image_path in image_paths:
        exif_data = parse_exif_data(image_path, project_info, analysis_folder, session_id)
        if exif_data:
            image_data_list.append(exif_data)

    grouped_images = group_images_by_time(image_data_list)
    logging.info(f"Total images processed: {len(grouped_images)}")
    return grouped_images
