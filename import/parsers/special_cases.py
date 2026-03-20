"""Special case handlers for Norwegian AIP parsing."""

import logging
from copy import deepcopy

logger = logging.getLogger(__name__)


class SpecialCaseHandler:
    """Base class for special case handlers."""
    
    def applies(self, aipname, line=None, ctx=None):
        raise NotImplementedError
    
    def handle(self, feature, ctx, line=None, **kwargs):
        raise NotImplementedError


class OsloNotamHandler(SpecialCaseHandler):
    """Handler for Oslo/Romerike NOTAM-only restricted areas."""
    
    def applies(self, aipname, line=None, ctx=None):
        if "EN R" not in aipname:
            return False
        if "Kongsvinger" in aipname:
            return True
        if "Romerike" in aipname:
            return True
        if "Oslo" in aipname and "102" not in aipname:
            return True
        return False
    
    def handle(self, feature, ctx, line=None, **kwargs):
        feature['properties']['notam_only'] = 'true'
        if "Romerike" in feature['properties'].get('name', '') or "Oslo" in feature['properties'].get('name', ''):
            feature['properties']['from (ft amsl)'] = '0'
            feature['properties']['from (m amsl)'] = '0'
            feature['properties']['to (ft amsl)'] = '99999'
            feature['properties']['to (m amsl)'] = '99999'
        logger.debug(f"Applied Oslo/Romerike NOTAM handler")
        return feature


class NotoddenHandler(SpecialCaseHandler):
    """Handler for Notodden TIZ multi-area parsing."""
    
    def __init__(self):
        self.in_notodden = False
        self.coord_blocks = []
        self.vertical_blocks = []
        self.current_coords = []
        
    def applies(self, aipname, line=None, ctx=None):
        return aipname and "Notodden TIZ" in aipname and "Notodden TIZ 2" not in aipname and "Notodden TIZ 3" not in aipname
    
    def start_collecting(self):
        self.in_notodden = True
        self.coord_blocks = []
        self.vertical_blocks = []
        self.current_coords = []
    
    def add_coordinate_line(self, line):
        self.current_coords.append(line.strip())
        if '(' in line and ')' in line:
            combined_coords = ' '.join(self.current_coords)
            self.coord_blocks.append(combined_coords)
            self.current_coords = []
    
    def add_vertical_limit(self, from_alt, to_alt):
        self.vertical_blocks.append((from_alt, to_alt))
    
    def is_ready(self):
        return len(self.coord_blocks) == 3 and len(self.vertical_blocks) == 3
    
    def get_features(self, base_feature, source, patterns):
        from util.utils import ft2m
        
        features = []
        for idx, (coord_str, (from_alt, to_alt)) in enumerate(zip(self.coord_blocks, self.vertical_blocks)):
            feature = deepcopy(base_feature)
            if idx == 0:
                feature['properties']['name'] = "Notodden TIZ"
            else:
                feature['properties']['name'] = f"Notodden TIZ {idx + 1}"
            
            if 'class' not in feature['properties'] or not feature['properties']['class']:
                feature['properties']['class'] = 'G'
            
            feature['properties']['from (ft amsl)'] = from_alt
            feature['properties']['from (m amsl)'] = ft2m(from_alt)
            feature['properties']['to (ft amsl)'] = to_alt
            feature['properties']['to (m amsl)'] = ft2m(to_alt)
            feature['properties']['aip'] = source
            feature['properties']['source'] = source
            feature['properties']['source_href'] = source
            
            obj = []
            coord_matches = patterns.re_coord3.findall(coord_str)
            for match in coord_matches:
                ne,n,e,along,arc,rad,cn,ce = match[:8]
                if n and e:
                    obj.insert(0, (n, e))
            
            feature['geometry'] = obj
            features.append(feature)
        
        self.in_notodden = False
        self.coord_blocks = []
        self.vertical_blocks = []
        
        return features


oslo_notam_handler = OsloNotamHandler()
notodden_handler = NotoddenHandler()
