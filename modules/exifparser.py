from datetime import datetime
import subprocess
import json
import os
import logging
from typing import List, Dict, Optional
from .database import db
from .utils.response import handle_exception
from .utils.constants import EXIFTOOL_PATH, GROUP_TIME_LIMIT

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def parse_exif_data_batch(image_paths: List[str]) -> List[Dict]:
    """ExifTool을 사용하여 여러 이미지의 EXIF 데이터를 한 번에 추출"""
    try:
        # Windows 경로를 정규화
        normalized_paths = [os.path.normpath(path) for path in image_paths]
        logger.info(f"Processing images with paths: {normalized_paths}")  # 디버깅용 로그
        
        result = subprocess.run(
            [EXIFTOOL_PATH, "-j"] + normalized_paths,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=30
        )
        
        if result.stderr:
            logger.warning(f"ExifTool warnings: {result.stderr}")
            
        if not result.stdout.strip():
            logger.warning("No EXIF data returned for batch processing")
            return []
            
        metadata_list = json.loads(result.stdout)
        return metadata_list
    except subprocess.TimeoutExpired:
        logger.error("ExifTool process timed out")
        return []
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse ExifTool output: {e}")
        return []
    except Exception as e:
        logger.error(f"Error in batch EXIF data parsing: {str(e)}")
        return []

def validate_project_info(project_info: Dict) -> bool:
    """프로젝트 정보 유효성 검사"""
    required_fields = ['name', 'id']
    return all(field in project_info for field in required_fields)

def create_exif_data(metadata: Dict, image_path: str, project_info: Dict, 
                    analysis_folder: str, session_id: str) -> Optional[Dict]:
    """EXIF 메타데이터로부터 구조화된 데이터 생성"""
    try:
        # SerialNumber 및 DateTimeOriginal 추출
        serial_number = metadata.get("SerialNumber", "UNKNOWN")
        date_time = metadata.get("DateTimeOriginal")

        if date_time:
            try:
                date_obj = datetime.strptime(date_time, '%Y:%m:%d %H:%M:%S')
            except ValueError:
                logger.warning(f"Invalid date format in {image_path}, using current time")
                date_obj = datetime.now()
        else:
            date_obj = datetime.now()
            logger.warning(f"No DateTimeOriginal found for {image_path}, using current time")

        # 파일명 생성
        seq = 1
        filename = date_obj.strftime('%Y%m%d-%H%M%S') + f's{seq}.jpg'

        # 파일 경로 구성 (project_info['id'] 사용)
        file_path = os.path.normpath(f"./mnt/{project_info['id']}/{analysis_folder}/source/{filename}")
        thumbnail_path = os.path.normpath(f"./mnt/{project_info['id']}/{analysis_folder}/thumbnail/thum_{filename}")

        return {
            "FileName": filename,
            "FilePath": file_path,
            "OriginalFileName": os.path.basename(image_path),
            "ThumnailPath": thumbnail_path,
            "SerialNumber": serial_number,
            "UserLabel": metadata.get("UserLabel", "UNKNOWN"),
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
    except Exception as e:
        logger.error(f"Error creating EXIF data structure: {str(e)}")
        return None

def assign_evtnum_to_group(images: List[Dict], evt_num: int) -> List[Dict]:
    """이미지 그룹에 evtnum 할당"""
    for img in images:
        img['evtnum'] = evt_num
    return images

def group_images_by_time(image_list: List[Dict]) -> List[Dict]:
    """시간 기준으로 이미지를 그룹화하고 evtnum 할당"""
    if not image_list:
        return []

    result = []
    evt_num = 1

    # SerialNumber와 FileName으로 그룹화
    grouped_by_serial = {}
    for img in image_list:
        key = f"{img['SerialNumber']}_{img['FileName']}"
        grouped_by_serial.setdefault(key, []).append(img)

    for group in grouped_by_serial.values():
        sorted_group = sorted(group, key=lambda x: x['DateTimeOriginal']['$date'])
        base_time = None
        current_group = []

        for img in sorted_group:
            current_time = datetime.fromisoformat(
                img['DateTimeOriginal']['$date'].replace('Z', '')
            )
            
            if not base_time or (current_time - base_time).total_seconds() / 60 <= GROUP_TIME_LIMIT:
                current_group.append(img)
                if base_time is None:
                    base_time = current_time
            else:
                result.extend(assign_evtnum_to_group(current_group, evt_num))
                current_group = [img]
                base_time = current_time
                evt_num += 1

        if current_group:
            result.extend(assign_evtnum_to_group(current_group, evt_num))
            evt_num += 1

    return result

def process_images(image_paths: List[str], project_info: Dict, 
                  analysis_folder: str, session_id: str) -> List[Dict]:
    """이미지 목록을 처리하고 MongoDB 저장용 데이터 생성"""
    try:
        if not image_paths:
            logger.warning("No images provided for processing")
            return []

        if not validate_project_info(project_info):
            raise ValueError("Invalid project_info structure")

        # 배치로 EXIF 데이터 추출
        metadata_list = parse_exif_data_batch(image_paths)
        if not metadata_list:
            logger.error("No EXIF data could be extracted from images")
            return []

        # EXIF 데이터 구조화
        image_data_list = []
        for metadata, image_path in zip(metadata_list, image_paths):
            exif_data = create_exif_data(
                metadata, image_path, project_info, analysis_folder, session_id
            )
            if exif_data:
                image_data_list.append(exif_data)

        # 시간별 그룹화
        grouped_images = group_images_by_time(image_data_list)
        logger.info(f"Successfully processed {len(grouped_images)} images")
        return grouped_images

    except Exception as e:
        logger.error(f"Error in process_images: {str(e)}")
        return []
