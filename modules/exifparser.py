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
def convert_gps_to_decimal(gps_data, ref):
    """
    EXIF GPS 데이터를 십진법(Decimal Degrees)으로 변환하는 함수
    gps_data: [도, 분, 초] 형식
    ref: 'N', 'S', 'E', 'W' 방향
    """
    try:
        degrees = float(gps_data[0])
        minutes = float(gps_data[1]) / 60
        seconds = float(gps_data[2]) / 3600
        decimal = degrees + minutes + seconds

        # 남반구(S) 또는 서경(W)일 경우 음수 처리
        if ref in ['S', 'W']:
            decimal *= -1

        return round(decimal, 6)  # 소수점 6자리까지 변환
    except Exception as e:
        logger.error(f"Error converting GPS data: {str(e)}")
        return None

def validate_project_info(project_info: Dict) -> bool:
    """프로젝트 정보 유효성 검사"""
    required_fields = ['name', 'id']
    return all(field in project_info for field in required_fields)

from datetime import datetime

def create_exif_data(metadata: Dict, image_path: str, project_info: Dict, 
                    analysis_folder: str, session_id: str) -> Optional[Dict]:
    """EXIF 메타데이터로부터 구조화된 데이터 생성"""
    try:
        serial_number = metadata.get("SerialNumber", "UNKNOWN")
        date_time = metadata.get("DateTimeOriginal")

        if date_time:
            try:
                # EXIF 날짜 포맷 변환
                date_obj = datetime.strptime(date_time, '%Y:%m:%d %H:%M:%S')
            except ValueError:
                logger.warning(f"Invalid date format in {image_path}, using current time")
                date_obj = datetime.utcnow()
        else:
            date_obj = datetime.utcnow()
            logger.warning(f"No DateTimeOriginal found for {image_path}, using current time")

        # MongoDB에 ISODate 형식으로 저장
        date_time_mongo = {"$date": date_obj.isoformat() + "Z"}

        # 위도/경도 추출
        latitude = metadata.get("GPSLatitude")
        longitude = metadata.get("GPSLongitude")

        # 위도/경도 값이 있을 때만 변환
        if latitude and longitude:
            try:
                latitude = convert_gps_to_decimal(latitude, metadata.get("GPSLatitudeRef", "N"))
                longitude = convert_gps_to_decimal(longitude, metadata.get("GPSLongitudeRef", "E"))
            except Exception as e:
                logger.warning(f"Failed to convert GPS coordinates for {image_path}: {e}")
                latitude = None
                longitude = None
        else:
            latitude = None
            longitude = None

        #  project_info에서 "ID" 키 확인
        project_id = project_info.get("ID") or project_info.get("id")
        if not project_id:
            logger.error(f"Project ID missing in project_info: {project_info}")
            return None

        # 파일명 생성
        base_name, ext = os.path.splitext(os.path.basename(image_path))  
        filename = f"{date_obj.strftime('%Y%m%d-%H%M%S')}s1{ext}"  
        thumbnail_filename = f"thum_{filename}"  

        # 경로 변환 (Flask 호환)
        file_path = f"/mnt/{project_id}/{analysis_folder}/source/{filename}".replace("\\", "/")
        thumbnail_path = f"/mnt/{project_id}/{analysis_folder}/thumbnail/{thumbnail_filename}".replace("\\", "/")

        return {
            "FileName": filename,  
            "FilePath": file_path,
            "OriginalFileName": os.path.basename(image_path),
            "ThumnailPath": thumbnail_path,
            "SerialNumber": serial_number,
            "UserLabel": metadata.get("UserLabel", "UNKNOWN"),
            "DateTimeOriginal": date_time_mongo,
            "Latitude": latitude,  
            "Longitude": longitude,  
            
            "ProjectInfo": {
                "ProjectName": project_info.get("ProjectName", "Unknown"),
                "ID": project_id  
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

def get_next_evtnum(project_id: str) -> int:
    """해당 프로젝트에서 가장 큰 evtnum을 찾아 +1을 반환"""
    last_entry = db.images.find({"ProjectInfo.ID": project_id}).sort("evtnum", -1).limit(1)
    last_evtnum = next(last_entry, {}).get("evtnum", 0)  
    return last_evtnum + 1  

GROUP_TIME_LIMIT = 5  #  5분 기준으로 그룹화

def group_images_by_time(image_list: List[Dict], project_id: str) -> List[Dict]:
    """
    프로젝트 ID를 고려하여 시간 기준으로 이미지를 그룹화하고 evtnum 할당
    (DB의 마지막 evtnum 기준으로 이어서 진행)
    """
    if not image_list:
        return []

    result = []
    evt_num = get_next_evtnum(project_id)  # 프로젝트 ID별 evtnum 가져오기

    # 같은 프로젝트, 같은 SerialNumber 내에서만 그룹핑
    grouped_by_project_serial = {}
    for img in image_list:
        key = f"{img['ProjectInfo']['ID']}_{img['SerialNumber']}"
        grouped_by_project_serial.setdefault(key, []).append(img)

    for group in grouped_by_project_serial.values():
        sorted_group = sorted(group, key=lambda x: x['DateTimeOriginal']['$date'])  # 시간순 정렬
        base_time = None
        current_group = []

        for img in sorted_group:
            current_time = datetime.fromisoformat(
                img['DateTimeOriginal']['$date'].replace('Z', '')
            )

            # 5분 이내 촬영된 이미지끼리만 같은 그룹으로 묶음
            if not base_time or (current_time - base_time).total_seconds() / 60 <= GROUP_TIME_LIMIT:
                current_group.append(img)
                if base_time is None:
                    base_time = current_time
            else:
                result.extend(assign_evtnum_to_group(current_group, evt_num))  # 현재 그룹에 evtnum 할당
                current_group = [img]
                base_time = current_time
                evt_num += 1  

        # 마지막 그룹 추가
        if current_group:
            result.extend(assign_evtnum_to_group(current_group, evt_num))
            evt_num += 1  

    return result


def process_images(image_paths: List[str], project_info: Dict, 
                  analysis_folder: str, session_id: str) -> List[Dict]:
    """이미지 목록을 처리하고 MongoDB 저장용 데이터 생성"""
    try:
        if not image_paths:
            logger.warning("⚠ No images provided for processing")
            return []

        if not validate_project_info(project_info):
            raise ValueError("Invalid project_info structure")

        #  EXIF 데이터 추출
        metadata_list = parse_exif_data_batch(image_paths)
        if not metadata_list:
            logger.error(" No EXIF data could be extracted from images")
            return []

        #  EXIF 데이터 구조화
        image_data_list = []
        for metadata, image_path in zip(metadata_list, image_paths):
            logger.info(f" Processing Image: {image_path}")  # 디버깅 로그

            exif_data = create_exif_data(
                metadata, image_path, project_info, analysis_folder, session_id
            )
            if not exif_data:
                logger.error(f" Failed to create EXIF data for {image_path}")
                continue

            logger.info(f" EXIF Data Created: {exif_data}")  # 디버깅 로그
            image_data_list.append(exif_data)

        #  시간별 그룹화 (DateTimeOriginal 확인)
        for img in image_data_list:
            logger.info(f" DateTimeOriginal: {img['DateTimeOriginal']}")  # 디버깅 로그

        grouped_images = group_images_by_time(image_data_list, project_info["id"])  # 프로젝트 ID 추가
        logger.info(f" Successfully processed {len(grouped_images)} images")
        return grouped_images

    except Exception as e:
        logger.error(f" Error in process_images: {str(e)}")
        return []
