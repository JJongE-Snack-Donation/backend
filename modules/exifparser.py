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
    
def get_all_evtnum_first_images(project_id: str, serial_number: str) -> List[Dict]:
    """
    해당 프로젝트 + SerialNumber에서 각 evtnum 그룹의 첫 번째 이미지를 가져옴.
    """
    pipeline = [
        {"$match": {"ProjectInfo.ID": project_id, "SerialNumber": serial_number}},  # SerialNumber 필터 적용
        {"$sort": {"evtnum": 1, "DateTimeOriginal": 1}},
        {"$group": {
            "_id": "$evtnum",
            "first_image": {"$first": "$$ROOT"}
        }},
        {"$replaceRoot": {"newRoot": "$first_image"}}
    ]
    return list(db.images.aggregate(pipeline))


def assign_evtnum_to_group(images: List[Dict], project_id: str, serial_number: str) -> List[Dict]:
    """
    새로운 이미지 그룹에 evtnum 할당할 때, 기존 그룹에서 가장 첫 번째 이미지와 비교하여 5분 초과 여부 결정.
    """
    if not images:
        return []

    # 기존 DB에서 해당 SerialNumber의 모든 evtnum 첫 이미지 가져오기
    evtnum_first_images = get_all_evtnum_first_images(project_id, serial_number)

    # 새로 업로드한 이미지 중 가장 첫 번째 촬영된 이미지 시간 가져오기
    sorted_images = sorted(images, key=lambda x: x["DateTimeOriginal"]["$date"])
    first_image_time = datetime.fromisoformat(sorted_images[0]["DateTimeOriginal"]["$date"].replace("Z", ""))

    new_evtnum = None

    if evtnum_first_images:
        for evtnum_data in evtnum_first_images:
            existing_time = datetime.fromisoformat(evtnum_data["DateTimeOriginal"]["$date"].replace("Z", ""))

            # 날짜(연-월-일)가 다르면 다른 그룹이어야 함
            if existing_time.date() != first_image_time.date():
                continue  

            # 5분 이내라면 같은 evtnum 사용
            if (first_image_time - existing_time).total_seconds() / 60 <= GROUP_TIME_LIMIT:
                new_evtnum = evtnum_data.get("evtnum")  
                break  

    # 기존 그룹과 매칭되지 않으면 새로운 evtnum 할당 (프로젝트 내에서 가장 큰 값 +1)
    if new_evtnum is None:
        new_evtnum = get_next_evtnum(project_id)

    # 이미지들에 evtnum 할당
    for img in images:
        img["evtnum"] = new_evtnum

    return images

def get_next_evtnum(project_id: str) -> int:
    """
    해당 프로젝트에서 가장 큰 evtnum을 찾아 +1을 반환.
    """
    last_entry = db.images.find_one(
        {"ProjectInfo.ID": project_id},  # 🔍 SerialNumber 고려 X, 프로젝트 전체 기준
        sort=[("evtnum", -1)]  # evtnum이 가장 큰 값을 가져옴
    )
    last_evtnum = last_entry.get("evtnum", 0) if last_entry else 0  # 없으면 0부터 시작
    return last_evtnum + 1  # 항상 프로젝트 기준으로 유일한 evtnum 보장



GROUP_TIME_LIMIT = 5  #  5분 기준으로 그룹화

def group_images_by_time(image_list: List[Dict], project_id: str) -> List[Dict]:
    """
    프로젝트 ID + SerialNumber 기준으로 시간별 그룹화하고 evtnum 할당.
    """
    if not image_list:
        return []

    result = []
    grouped_by_project_serial = {}

    # 같은 프로젝트, 같은 SerialNumber 내에서 그룹핑
    for img in image_list:
        key = f"{img['ProjectInfo']['ID']}_{img['SerialNumber']}"
        grouped_by_project_serial.setdefault(key, []).append(img)

    for key, group in grouped_by_project_serial.items():
        project_id, serial_number = key.split("_")

        # 기존 DB의 모든 evtnum 그룹의 첫 번째 이미지 목록 가져오기
        evtnum_info_list = get_all_evtnum_first_images(project_id, serial_number)

        # 새로운 업로드 이미지 정렬
        sorted_group = sorted(group, key=lambda x: x['DateTimeOriginal']['$date'])
        
        logger.info(f"Processing SerialNumber: {serial_number}, Total Images: {len(sorted_group)}")
        logger.info(f"Existing evtnum groups: {evtnum_info_list}")

        # evtnum 할당
        assigned_group = assign_evtnum_to_group(sorted_group, project_id, serial_number)
        
        # 디버깅 로그 추가: evtnum이 정상적으로 부여되었는지 확인
        for img in assigned_group:
            logger.info(f"Image: {img['OriginalFileName']} -> evtnum: {img.get('evtnum')}")

        result.extend(assigned_group)

    return result

def batch_processing(image_paths: List[str], batch_size: int = 100) -> List[List[str]]:
    """이미지를 batch_size 개수만큼 나누는 함수"""
    return [image_paths[i:i + batch_size] for i in range(0, len(image_paths), batch_size)]

def process_images(image_paths: List[str], project_info: Dict, 
                  analysis_folder: str, session_id: str) -> List[Dict]:
    """이미지를 100개씩 나누어 처리하고 MongoDB 저장용 데이터 생성"""
    try:
        if not image_paths:
            logger.warning("⚠ No images provided for processing")
            return []

        if not validate_project_info(project_info):
            raise ValueError("Invalid project_info structure")

        grouped_images = []  # 최종 결과 리스트

        # 100개씩 나누어 배치 처리
        image_batches = batch_processing(image_paths, batch_size=100)
        for batch_idx, image_batch in enumerate(image_batches):
            logger.info(f"Processing batch {batch_idx + 1}/{len(image_batches)} with {len(image_batch)} images")

            #  EXIF 데이터 추출
            metadata_list = parse_exif_data_batch(image_batch)
            if not metadata_list:
                logger.error(f" No EXIF data could be extracted from batch {batch_idx + 1}")
                continue

            #  EXIF 데이터 구조화
            image_data_list = []
            for metadata, image_path in zip(metadata_list, image_batch):
                logger.info(f" Processing Image: {image_path}")

                exif_data = create_exif_data(
                    metadata, image_path, project_info, analysis_folder, session_id
                )
                if not exif_data:
                    logger.error(f" Failed to create EXIF data for {image_path}")
                    continue

                # 추가 로그: DateTimeOriginal 필드 확인
                if "DateTimeOriginal" not in exif_data:
                    logger.error(f"DateTimeOriginal 키가 없음! {exif_data}")
                else:
                    logger.info(f"✔ DateTimeOriginal 확인: {exif_data['DateTimeOriginal']}")

                logger.info(f" EXIF Data Created: {exif_data}")
                image_data_list.append(exif_data)

            #  시간별 그룹화
            for img in image_data_list:
                logger.info(f" DateTimeOriginal: {img['DateTimeOriginal']}")

            batch_grouped_images = group_images_by_time(image_data_list, project_info["id"])
            grouped_images.extend(batch_grouped_images)  # 전체 리스트에 추가

        logger.info(f" Successfully processed {len(grouped_images)} images in total")
        return grouped_images

    except Exception as e:
        logger.error(f" Error in process_images: {str(e)}")
        return []